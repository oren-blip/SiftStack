"""SmartSkip bulk-skip API client (api.smartskip.io).

SmartSkip's public line is that they deliberately do NOT offer an API, and their
own blog argues CSV beats one. That is about a *published* API. The SPA itself
runs on a normal REST backend, and Ty's deep-prospecting-v5 skill reverse-
engineered and verified the contract (`references/smartskip-api.md`, 2026-07-29).
This is the same relationship SiftStack already has with DataSift's apiv2.
Re-verified against Oren's live account 2026-09-09.

THE ONLY CALL THAT COSTS MONEY IS payment_intent(). Steps 1-4 are free and
idempotent -- each upload mints a fresh bulkSkipId and orphaned unpaid uploads
are harmless and invisible in the account. So the flow deliberately stops after
`calculate`, reports the real billable row count, and refuses to pay unless the
caller passes an explicit ceiling it fits under.

Lifecycle:
    1. POST /bulk-skip/mapping            multipart file=<csv>  -> bulkSkipId
    2. GET  /bulk-skip/fields             the mappable field names
    3. POST /bulk-skip/fields/{id}        {"schema": {apiField: "CSV Header"}}
    4. POST /bulk-skip/calculate/{id}     FREE -> {entities, duplicates, ...}
    5. POST /bulk-skip/payment-intent     BILLS THE CARD
    6. GET  /bulk-skip?sortField=...      poll status (PAID orders only)
    7. GET  /bulk-skip/download/{id}?type=vertical   the campaign-format CSV

Access tokens live ~15 min, refresh tokens ~30 days; the session is cached and
auto-refreshed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests

try:                                    # credentials live in .env, same as the
    from dotenv import load_dotenv      # rest of the project
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:                     # pragma: no cover
    pass

logger = logging.getLogger(__name__)

BASE = "https://api.smartskip.io"
SESSION_FILE = Path("output/.smartskip_session.json")
STATE_FILE = Path("output/.smartskip_orders.json")
COST_PER_ROW = 0.15

# Our UPLOAD_COLUMNS -> their apiField. middleName is deliberately NOT mapped:
# putting anything there poisons every search (verified on the mapping screen).
SCHEMA = {
    "firstName": "First Name",
    "lastName": "Last Name",
    "mailingAddress": "Mailing Address",
    "mailingCity": "Mailing City",
    "mailingState": "Mailing State",
    "mailingZip": "Mailing Zip",
    "propertyAddress": "Property Address",
    "propertyCity": "Property City",
    "propertyState": "Property State",
    "propertyZip": "Property Zip",
}


class SmartSkipError(RuntimeError):
    pass


@dataclass
class Order:
    bulk_skip_id: str
    entities: int = 0
    duplicates: int = 0
    file_name: str = ""

    @property
    def cost(self) -> float:
        return self.entities * COST_PER_ROW


class SmartSkip:
    def __init__(self, email: str | None = None, password: str | None = None):
        self.email = email or os.getenv("SMARTSKIP_EMAIL") or ""
        self.password = password or os.getenv("SMARTSKIP_PASSWORD") or ""
        if not (self.email and self.password):
            raise SmartSkipError(
                "set SMARTSKIP_EMAIL and SMARTSKIP_PASSWORD (they live in .env)")
        self._access = ""
        self._refresh = ""
        self._load_session()

    # ── auth ──────────────────────────────────────────────────────────────
    def _load_session(self) -> None:
        try:
            d = json.loads(SESSION_FILE.read_text())
            self._access, self._refresh = d.get("access", ""), d.get("refresh", "")
        except (OSError, ValueError):
            pass

    def _save_session(self) -> None:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps(
            {"access": self._access, "refresh": self._refresh}))

    def _signin(self) -> None:
        r = requests.post(f"{BASE}/auth/signin",
                          json={"email": self.email, "password": self.password},
                          timeout=60)
        if r.status_code >= 300:
            raise SmartSkipError(f"signin failed HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        self._access, self._refresh = d["accessToken"], d.get("refreshToken", "")
        self._save_session()
        logger.info("SmartSkip: signed in as %s", self.email)

    def _try_refresh(self) -> bool:
        if not self._refresh:
            return False
        r = requests.get(f"{BASE}/auth/refresh",
                         headers={"Authorization": f"Bearer {self._refresh}"},
                         timeout=60)
        if r.status_code >= 300:
            return False
        d = r.json()
        self._access = d.get("accessToken", "")
        self._refresh = d.get("refreshToken", self._refresh)
        self._save_session()
        return bool(self._access)

    def _call(self, method: str, path: str, **kw) -> requests.Response:
        """One request, transparently re-authing on a 401."""
        if not self._access:
            self._signin()
        for attempt in (1, 2):
            h = dict(kw.pop("headers", {}) or {})
            h["Authorization"] = f"Bearer {self._access}"
            r = requests.request(method, f"{BASE}{path}", headers=h, timeout=180, **kw)
            if r.status_code != 401 or attempt == 2:
                return r
            if not self._try_refresh():
                self._signin()
        return r  # unreachable, keeps type checkers happy

    # ── free steps ────────────────────────────────────────────────────────
    def upload(self, csv_path: Path) -> Order:
        with Path(csv_path).open("rb") as f:
            r = self._call("POST", "/bulk-skip/mapping",
                           files={"file": (Path(csv_path).name, f, "text/csv")})
        if r.status_code >= 300:
            raise SmartSkipError(f"upload failed HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        bid = d.get("bulkSkipId") or d.get("_id")
        if not bid:
            raise SmartSkipError(f"no bulkSkipId in upload response: {r.text[:300]}")
        logger.info("SmartSkip: uploaded %s -> %s", Path(csv_path).name, bid)
        return Order(bulk_skip_id=bid, file_name=Path(csv_path).name)

    def map_fields(self, order: Order, schema: dict | None = None) -> dict:
        r = self._call("POST", f"/bulk-skip/fields/{order.bulk_skip_id}",
                       json={"schema": schema or SCHEMA})
        if r.status_code >= 300:
            raise SmartSkipError(f"field mapping failed HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    def calculate(self, order: Order) -> Order:
        """FREE. Returns the billable row count -- the number to sanity-check."""
        r = self._call("POST", f"/bulk-skip/calculate/{order.bulk_skip_id}")
        if r.status_code >= 300:
            raise SmartSkipError(f"calculate failed HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        order.entities = int(d.get("entities") or 0)
        order.duplicates = int(d.get("duplicates") or 0)
        order.file_name = d.get("fileName") or order.file_name
        logger.info("SmartSkip: %d billable row(s), %d duplicate(s) -> $%.2f",
                    order.entities, order.duplicates, order.cost)
        return order

    # ── the one that spends money ─────────────────────────────────────────
    def default_payment_method(self) -> dict | None:
        r = self._call("GET", "/payment/payment-method")
        if r.status_code >= 300:
            return None
        cards = r.json() or []
        return next((c for c in cards if c.get("isDefault")), cards[0] if cards else None)

    def pay(self, order: Order, max_spend: float) -> dict:
        """BILLS THE CARD. Refuses if the calculated cost exceeds max_spend."""
        if order.entities <= 0:
            raise SmartSkipError("refusing to pay: calculate() returned 0 rows")
        if order.cost > max_spend:
            raise SmartSkipError(
                f"refusing to pay ${order.cost:.2f} for {order.entities} row(s): "
                f"over the ${max_spend:.2f} ceiling. Raise --max-spend deliberately.")
        card = self.default_payment_method()
        if not card:
            raise SmartSkipError("no saved card on the SmartSkip account")
        r = self._call("POST", "/bulk-skip/payment-intent",
                       json={"bulkSkipId": order.bulk_skip_id,
                             "paymentMethodId": card["id"]})
        if r.status_code >= 300:
            raise SmartSkipError(f"payment failed HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        if d.get("clientSecret"):
            raise SmartSkipError(
                "the card needs 3-D Secure confirmation, which only the browser can "
                "do. Pay this order at smartskip.io, then run `fetch`.")
        logger.info("SmartSkip: PAID $%.2f on %s ****%s (%s)", order.cost,
                    card.get("brand"), card.get("last4"), d.get("status"))
        return d

    # ── after payment ─────────────────────────────────────────────────────
    def status(self, bulk_skip_id: str) -> str:
        """Paid orders only -- unpaid ones never appear in this list."""
        r = self._call("GET", "/bulk-skip",
                       params={"sortField": "createdAt", "sortOrder": "desc"})
        if r.status_code >= 300:
            return "unknown"
        for it in (r.json() or {}).get("items", []):
            if it.get("_id") == bulk_skip_id:
                return it.get("status") or "unknown"
        return "not-listed"

    def wait(self, bulk_skip_id: str, timeout: int = 3600, every: int = 30) -> str:
        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            s = self.status(bulk_skip_id)
            if s != last:
                logger.info("SmartSkip: status = %s", s)
                last = s
            if s.lower() in ("completed", "complete", "error", "failed"):
                return s
            time.sleep(every)
        return last or "timeout"

    def download(self, bulk_skip_id: str, out: Path,
                 fmt: str = "vertical") -> Path:
        """vertical == the Campaign Format our parser reads."""
        r = self._call("GET", f"/bulk-skip/download/{bulk_skip_id}",
                       params={"type": fmt})
        if r.status_code >= 300:
            raise SmartSkipError(f"download failed HTTP {r.status_code}: {r.text[:200]}")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        logger.info("SmartSkip: wrote %s (%d bytes)", out, len(r.content))
        return out


# ── tiny local ledger, because unpaid orders vanish from their list ───────
def remember(order: Order, extra: dict | None = None) -> None:
    try:
        d = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        d = {}
    d[order.bulk_skip_id] = {"file": order.file_name, "entities": order.entities,
                            "cost": round(order.cost, 2),
                            "when": time.strftime("%Y-%m-%d %H:%M"), **(extra or {})}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(d, indent=1))


def orders() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}
