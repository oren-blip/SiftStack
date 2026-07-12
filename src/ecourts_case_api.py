"""eCourts case detail OData REST client.

The Odyssey portal (`portal-nc.tylertech.cloud`) exposes a clean
OData service at `/app/RegisterOfActionsService/` that returns every
case detail piece as JSON. No login required — just the AWS WAF cookie
(already managed by `ecourts_scraper.py`).

The most useful endpoint for probate work is `Parties('{hex_id}')`,
which returns the decedent + executor (called "Affiant" in NC small
estates) + beneficiaries + attorney, each with a structured Addresses
array. This is what the user's manual FTM-style weekly sheets contain.

The hex id comes from each `a.caseLink` element in the search results
page: `data-url="/app/RegisterOfActions/?id={256-char hex}&...".`
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)


BASE = "https://portal-nc.tylertech.cloud/app/RegisterOfActionsService"
REFERER = "https://portal-nc.tylertech.cloud/app/RegisterOfActions/"
ORIGIN = "https://portal-nc.tylertech.cloud"


# ── Output dataclasses ────────────────────────────────────────────────


@dataclass
class CaseAddress:
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""

    # Odyssey returns a street either as a flat AddressLine1 OR — far more
    # often — as structured components with AddressLine1 = null:
    #   {"Block": "1433", "PrefixDirection": null, "Street": "Poston",
    #    "AddressSuffixKey": "DR", "PostfixDirection": null,
    #    "UnitKey": null, "UnitNumber": null, "AddressLine1": null, ...}
    # Reading only AddressLine1 silently threw away every street in that form.
    # That is why heir-occupancy never fired (it compares street to the
    # property address), why the Beneficiaries column had no streets, and why
    # PR mailing addresses fell through to a people-search guess.
    _LINE1_PARTS = ("Block", "PrefixDirection", "Street", "AddressSuffixKey", "PostfixDirection")

    @staticmethod
    def _compose_line1(obj: dict) -> str:
        """Rebuild '1433 Poston Dr' / '410 S Thompson St' from components."""
        parts = [str(obj.get(k) or "").strip() for k in CaseAddress._LINE1_PARTS]
        return " ".join(p for p in parts if p)

    @staticmethod
    def _compose_line2(obj: dict) -> str:
        """'APT 614' from UnitKey + UnitNumber."""
        unit = " ".join(
            str(obj.get(k) or "").strip() for k in ("UnitKey", "UnitNumber")
        ).strip()
        return unit

    @classmethod
    def from_json(cls, obj: dict) -> "CaseAddress":
        line1 = (obj.get("AddressLine1") or "").strip() or cls._compose_line1(obj)
        line2 = (obj.get("AddressLine2") or "").strip() or cls._compose_line2(obj)
        return cls(
            line1=line1,
            line2=line2,
            city=(obj.get("City") or "").strip(),
            state=(obj.get("State") or "").strip(),
            zip=(obj.get("PostalCode") or "").strip(),
        )

    def is_blank(self) -> bool:
        return not (self.line1 or self.city or self.zip)


@dataclass
class CaseParty:
    """One party on an eCourts case (decedent / executor / beneficiary / etc)."""
    connection_type: str = ""        # "Decedent" / "Affiant" / "Beneficiary" / ...
    full_name: str = ""               # FormattedName as returned (e.g. "Phifer, Warren")
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    suffix: str = ""
    addresses: list[CaseAddress] = field(default_factory=list)

    @property
    def first_address(self) -> CaseAddress:
        return self.addresses[0] if self.addresses else CaseAddress()

    @classmethod
    def from_json(cls, obj: dict) -> "CaseParty":
        return cls(
            connection_type=(obj.get("ConnectionType") or "").strip(),
            full_name=(obj.get("FormattedName") or "").strip(),
            first_name=(obj.get("NameFirst") or "").strip(),
            middle_name=(obj.get("NameMid") or "").strip(),
            last_name=(obj.get("NameLast") or "").strip(),
            suffix=(obj.get("NameSuffix") or "").strip(),
            addresses=[CaseAddress.from_json(a) for a in (obj.get("Addresses") or [])],
        )


@dataclass
class CaseDetail:
    """Aggregated case detail derived from the Parties endpoint."""
    case_id: str = ""                 # Odyssey internal CaseId
    parties: list[CaseParty] = field(default_factory=list)

    # Connection types Odyssey may use for the deceased person across NC
    # counties. Mecklenburg uses "Decedent"; Cabarrus case 26E000566-120
    # (Bonds, Bobby Ray) returned a party set with the PR (Voight) found
    # but no party with literal "decedent" type, leaving the search-results
    # caption name in place — proof at least one county uses a different label.
    _DECEDENT_TYPES = {
        "decedent",
        "deceased",
        "deceased person",
        "estate",
        "estate of",
        "subject",
    }

    # Convenience accessors — these are what the FTM-style output needs
    @property
    def decedent(self) -> CaseParty | None:
        for p in self.parties:
            if p.connection_type.lower() in self._DECEDENT_TYPES:
                return p
        return None

    # NC Estates connection types — verified against 10-case Mecklenburg sample (2026-05-17).
    # Affiant = small-estate affidavit petitioner
    # Applicant = applicant for letters of administration (most common in full estates)
    # Personal Representative / Executor* / Administrator* = formal appointments
    _EXECUTOR_TYPES = {
        "affiant",
        "applicant",
        "executor", "executrix",
        "administrator", "administratrix",
        "personal representative", "personal rep",
        "petitioner",
    }
    # Fallback contact when no formal executor on file yet (case just opened)
    _FALLBACK_CONTACT_TYPES = {
        "next of kin",
        "interested person",
    }
    # Role qualifiers the court prepends that don't change the underlying role:
    # "Co-Executor", "Successor Administrator", "Substitute Trustee", etc. Stripped
    # before matching so a Co-Executor is recognized as an executor. Without this,
    # exact-set membership silently misses every co-appointment (Titterington
    # 26E000789-170: sole party was "Co-Executor: Riggleman" → wrongly "Heirs of").
    _ROLE_QUALIFIER_PREFIXES = (
        "co-", "co ",
        "successor ", "substitute ", "temporary ", "acting ",
        "ancillary ", "limited ", "collector ",
    )

    @classmethod
    def _normalize_role(cls, connection_type: str) -> str:
        role = (connection_type or "").strip().lower()
        changed = True
        while changed:
            changed = False
            for pref in cls._ROLE_QUALIFIER_PREFIXES:
                if role.startswith(pref):
                    role = role[len(pref):].strip()
                    changed = True
        return role
    _BENEFIT_TYPES = {"beneficiary", "heir", "devisee", "legatee", "next of kin"}
    # Guardianship party types — these mark a case as a guardianship (living
    # incapacitated person), not a probate of a decedent
    _GUARDIANSHIP_TYPES = {
        "ward",
        "guardian of the person", "guardian of the estate", "guardian of the person and estate",
        "guardian ad litem",
        "special fiduciary (35a article ii)",
    }

    @property
    def is_guardianship(self) -> bool:
        """True when the case is a guardianship of a living person, not a decedent estate."""
        for p in self.parties:
            if self._normalize_role(p.connection_type) in self._GUARDIANSHIP_TYPES:
                return True
        return False

    @property
    def executor(self) -> CaseParty | None:
        """The personal representative on file (Affiant/Applicant/Executor/etc).

        Falls back to Next of Kin or Interested Person when no formal
        executor exists (common for recently-opened cases).
        """
        for p in self.parties:
            if self._normalize_role(p.connection_type) in self._EXECUTOR_TYPES:
                return p
        for p in self.parties:
            if self._normalize_role(p.connection_type) in self._FALLBACK_CONTACT_TYPES:
                return p
        return None

    @property
    def beneficiaries(self) -> list[CaseParty]:
        return [p for p in self.parties if self._normalize_role(p.connection_type) in self._BENEFIT_TYPES]


# ── ID extraction ─────────────────────────────────────────────────────


_ID_RE = re.compile(r"[?&]id=([0-9A-F]+)", re.IGNORECASE)


def extract_case_id(data_url: str) -> str:
    """Pull the 256-char hex id from a `data-url` attribute on a caseLink."""
    if not data_url:
        return ""
    m = _ID_RE.search(data_url)
    return m.group(1) if m else ""


# ── HTTP client ───────────────────────────────────────────────────────


class CaseDetailClient:
    """Thin OData client for the Register of Actions service.

    Stateless other than the requests Session (for connection pooling).
    All WAF/UA/cookies are passed per-call so the caller can rotate them
    when the WAF token expires.
    """

    def __init__(self, *, waf_token: str, user_agent: str):
        self.waf_token = waf_token
        self.user_agent = user_agent
        self._session = requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Referer": REFERER,
            "Origin": ORIGIN,
        }

    def _cookies(self) -> dict[str, str]:
        return {"aws-waf-token": self.waf_token} if self.waf_token else {}

    def fetch_parties(self, case_id: str, *, retries: int = 2) -> list[CaseParty]:
        """GET /Parties('{id}') and return parsed party objects.

        HTTP 202 (Accepted) is Odyssey's "request queued, retry in a moment"
        signal — back off and retry. After ~2 attempts we give up and
        return empty (caller can retry later).
        """
        if not case_id:
            return []
        url = f"{BASE}/Parties('{case_id}')?mode=portalembed&$top=50&$skip=0"
        for attempt in range(retries + 1):
            try:
                r = self._session.get(url, headers=self._headers(), cookies=self._cookies(), timeout=30)
            except requests.RequestException as e:
                logger.warning("eCourts API: parties fetch failed (attempt %d): %s", attempt + 1, e)
                if attempt < retries:
                    time.sleep(3 + attempt * 3)
                    continue
                return []
            if r.status_code == 200:
                try:
                    data = r.json()
                except ValueError as e:
                    logger.warning("eCourts API: invalid JSON: %s; raw: %.200s", e, r.text)
                    return []
                return [CaseParty.from_json(p) for p in (data.get("Parties") or [])]
            if r.status_code == 202:
                # Queued — wait for the data to be ready
                wait = 5 + attempt * 5
                logger.info("eCourts API: HTTP 202 on Parties (attempt %d) — waiting %ds", attempt + 1, wait)
                if attempt < retries:
                    time.sleep(wait)
                    continue
                return []
            if r.status_code in (401, 403):
                logger.error(
                    "eCourts API: HTTP %d on Parties — WAF cookie likely expired",
                    r.status_code,
                )
                return []
            logger.warning("eCourts API: HTTP %d on Parties (attempt %d)", r.status_code, attempt + 1)
            if attempt < retries:
                time.sleep(2 + attempt * 2)
        return []

    def fetch_detail(self, case_id: str) -> CaseDetail:
        parties = self.fetch_parties(case_id)
        return CaseDetail(case_id=case_id, parties=parties)
