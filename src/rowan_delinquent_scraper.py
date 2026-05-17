"""Scrape Rowan County's annual delinquent property tax list.

Source: https://www.rowancountync.gov/1525/Delinquent-Taxpayer-Lists
Each year, the county publishes a structured XLSX (and PDF backup). The
XLSX is a flat dump of every delinquent bill with 71 columns including
owner name + mailing address, parcel number, balance due, and a REAL/PP
report-group flag. ~9,000 records per year.

Architecture: pure HTTP + openpyxl. No browser automation needed.

Discovery: the landing page lists multiple years with anchor text like
"Download 2025 List (XLS)" linked to /DocumentCenter/View/<id>. We grep
the page for that pattern and pick the most recent year's URL.

Caveats:
- The XLSX has the taxpayer's MAILING address (where the bill goes),
  not necessarily the property address. For owner-occupied residential
  these are usually the same; for landlords/heirs/estates they may not be.
- We filter to REAL property (report_group_description == 'REAL') to skip
  personal-property bills (boats, business equipment, etc).
- We further filter by balance_due >= a minimum (default $1,000) to skip
  noise like sub-$100 leftover bills.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
import requests

import config
from notice_parser import NoticeData

logger = logging.getLogger(__name__)


LANDING_URL = "https://www.rowancountync.gov/1525/Delinquent-Taxpayer-Lists"
BASE = "https://www.rowancountync.gov"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
}

# Column indices in the BILL_EXPORT_YYYY sheet (verified against 2025 file)
COL = {
    "tax_year":            4,
    "report_group":        5,    # "REAL" or "PP"
    "bill_number":         7,
    "owner_name_1":        9,
    "owner_name_2":       10,
    "addr_line_1":        11,
    "addr_line_2":        12,
    "city":               13,
    "state":              14,
    "zip":                15,
    "parcel":             16,
    "assessed_value":     17,
    "total_due":          20,
    "balance_due":        26,
    "legal_desc_1":       32,
}


# ── State helpers ─────────────────────────────────────────────────────


def _state_file() -> Path:
    return config.PROJECT_ROOT / "rowan_delinquent_last_run.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "rowan_delinquent_seen_ids.json"


def load_last_run_date() -> str | None:
    return config.load_state(_state_file()).get("last_run_date")


def save_last_run_date() -> None:
    config.save_state(_state_file(), {"last_run_date": datetime.now().strftime("%Y-%m-%d")})


def load_seen_ids() -> dict[str, str]:
    data = config.load_state(_seen_ids_file())
    if not data:
        return {}
    cutoff = (datetime.now() - timedelta(days=config.SEEN_IDS_PRUNE_DAYS)).strftime("%Y-%m-%d")
    return {nid: d for nid, d in data.items() if d >= cutoff}


def save_seen_ids(seen: dict[str, str]) -> None:
    config.save_state(_seen_ids_file(), seen)


# ── Discovery ─────────────────────────────────────────────────────────


# Page has links like:
#   <a href="/DocumentCenter/View/55256" ...>Download 2025 List (XLS)</a>
XLS_LINK_RE = re.compile(
    r'href="(/DocumentCenter/View/\d+)"[^>]*>Download\s+(\d{4})\s+List\s+\(XLS\)',
    re.IGNORECASE,
)


def discover_latest_xlsx_url(session: requests.Session) -> tuple[str, int] | None:
    """Walk the landing page and find the highest-year XLSX download URL."""
    try:
        r = session.get(LANDING_URL, headers=HEADERS, timeout=20)
    except Exception as e:
        logger.error("Rowan: landing-page fetch failed: %s", e)
        return None
    if r.status_code != 200:
        logger.error("Rowan: landing page HTTP %d", r.status_code)
        return None

    candidates = XLS_LINK_RE.findall(r.text)
    if not candidates:
        logger.error("Rowan: no XLS download links found on landing page")
        return None

    # Pick the most recent year
    candidates.sort(key=lambda t: int(t[1]), reverse=True)
    href, year = candidates[0]
    url = BASE + href if href.startswith("/") else href
    return url, int(year)


# ── XLSX parsing ──────────────────────────────────────────────────────


def fetch_xlsx(session: requests.Session, url: str) -> bytes | None:
    try:
        r = session.get(url, headers=HEADERS, timeout=60)
    except Exception as e:
        logger.error("Rowan: XLSX download failed: %s", e)
        return None
    if r.status_code != 200:
        logger.error("Rowan: XLSX HTTP %d (url=%s)", r.status_code, url)
        return None
    return r.content


def parse_xlsx(
    xlsx_bytes: bytes,
    *,
    min_balance: float = 1000.0,
    real_only: bool = True,
) -> list[dict]:
    """Yield dict-per-bill from the BILL_EXPORT_<year> sheet."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    # The active sheet is BILL_EXPORT_<year>; fall back to first sheet that has data
    ws = wb.active
    rows: list[dict] = []
    row_iter = ws.iter_rows(values_only=True)
    headers = next(row_iter, None)  # consume header row
    if not headers:
        return rows

    for raw in row_iter:
        if not raw or len(raw) <= COL["balance_due"]:
            continue
        report_group = (raw[COL["report_group"]] or "").strip().upper() if isinstance(raw[COL["report_group"]], str) else (raw[COL["report_group"]] or "")
        if real_only and report_group != "REAL":
            continue
        try:
            balance = float(raw[COL["balance_due"]] or 0)
        except (TypeError, ValueError):
            balance = 0.0
        if balance < min_balance:
            continue
        rows.append({
            "tax_year":       raw[COL["tax_year"]],
            "bill_number":   (raw[COL["bill_number"]] or "").strip() if isinstance(raw[COL["bill_number"]], str) else raw[COL["bill_number"]],
            "owner_name":    (raw[COL["owner_name_1"]] or "").strip() if isinstance(raw[COL["owner_name_1"]], str) else (raw[COL["owner_name_1"]] or ""),
            "owner_name_2":  raw[COL["owner_name_2"]],
            "addr_line_1":   raw[COL["addr_line_1"]],
            "addr_line_2":   raw[COL["addr_line_2"]],
            "city":          raw[COL["city"]],
            "state":         raw[COL["state"]],
            "zip":           raw[COL["zip"]],
            "parcel":        raw[COL["parcel"]],
            "assessed":      raw[COL["assessed_value"]],
            "total_due":     raw[COL["total_due"]],
            "balance_due":   balance,
            "legal_desc":    raw[COL["legal_desc_1"]],
        })
    return rows


def row_to_notice(row: dict, year: int) -> NoticeData:
    """Map one Rowan delinquent-bill row → NoticeData."""
    owner = str(row.get("owner_name") or "").strip()
    addr1 = str(row.get("addr_line_1") or "").strip()
    addr2 = str(row.get("addr_line_2") or "").strip()
    city = str(row.get("city") or "").strip().title()
    state = str(row.get("state") or "").strip().upper() or "NC"
    zipc = str(row.get("zip") or "").strip()[:5]
    parcel = str(row.get("parcel") or "").strip()
    bill_no = str(row.get("bill_number") or "").strip()
    balance = row.get("balance_due", 0)

    # The XLSX gives us the OWNER's mailing address. For our pipeline that's
    # the contact address (owner_*); the property address is not in this feed.
    notice = NoticeData(
        county="Rowan",
        state="NC",
        notice_type="tax_delinquent",
        date_added=datetime.now().strftime("%Y-%m-%d"),
        owner_name=owner.title() if owner.isupper() else owner,
        owner_street=(addr1 + (" " + addr2 if addr2 else "")).title() if addr1.isupper() else (addr1 + (" " + addr2 if addr2 else "")),
        owner_city=city,
        owner_state=state,
        owner_zip=zipc,
        parcel_id=parcel,
        tax_delinquent_amount=f"{balance:.2f}",
        tax_delinquent_years=str(year),
        source_url=f"{LANDING_URL}#bill={bill_no}",
        raw_text=(
            f"Rowan County NC delinquent property tax bill (year {year}). "
            f"Bill {bill_no}, parcel {parcel}. "
            f"Owner: {owner}. Mailing: {addr1}, {city} {state} {zipc}. "
            f"Balance due: ${balance:.2f} on assessed value ${row.get('assessed') or 'n/a'}. "
            f"Legal: {row.get('legal_desc') or 'n/a'}."
        ),
    )
    return notice


# ── Public entry ─────────────────────────────────────────────────────


def scrape_rowan_delinquent(
    *,
    min_balance: float = 1000.0,
    seen_ids: dict[str, str] | None = None,
    max_records: int = 0,
) -> list[NoticeData]:
    """Fetch Rowan's most recent annual delinquent-tax XLSX and return notices.

    Args:
        min_balance: skip bills with balance_due below this (default $1,000).
        seen_ids:    cross-run dedup cache keyed by bill_number.
        max_records: stop after this many (0 = all).
    """
    if seen_ids is None:
        seen_ids = load_seen_ids()
    logger.info("Rowan delinquent: %d seen IDs", len(seen_ids))

    session = requests.Session()
    discovered = discover_latest_xlsx_url(session)
    if not discovered:
        return []
    xlsx_url, year = discovered
    logger.info("Rowan delinquent: most recent list = %d at %s", year, xlsx_url)

    xlsx_bytes = fetch_xlsx(session, xlsx_url)
    if not xlsx_bytes:
        return []
    logger.info("Rowan delinquent: downloaded %d bytes", len(xlsx_bytes))

    rows = parse_xlsx(xlsx_bytes, min_balance=min_balance, real_only=True)
    logger.info(
        "Rowan delinquent: %d REAL-property bills with balance >= $%.0f",
        len(rows), min_balance,
    )

    notices: list[NoticeData] = []
    for row in rows:
        bill_no = str(row.get("bill_number") or "").strip()
        if not bill_no:
            continue
        if bill_no in seen_ids:
            continue
        notices.append(row_to_notice(row, year))
        seen_ids[bill_no] = notices[-1].date_added
        if max_records and len(notices) >= max_records:
            break

    save_seen_ids(seen_ids)
    save_last_run_date()
    logger.info("Rowan delinquent: returned %d notice(s)", len(notices))
    return notices
