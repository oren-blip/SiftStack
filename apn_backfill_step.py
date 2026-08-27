"""APN backfill sweep: stamp missing parcel numbers on land records in the
NSM flow, from the pipeline's own weekly CSVs. Free — no paid APIs.

Why this exists (2026-08-26): the upload CSV deliberately dropped its APN
column on 2026-07-12 on the belief that DataSift's parcel field is
enrichment-controlled and ignores an uploaded APN. That's true of the upload
wizard, but the field IS writable by API PATCH (proven on the Kluttz record
2026-08-17 and again on 9 records 2026-08-26). DataSift's enrich resolves
parcels by ADDRESS, so numbered-street records heal on their own — but vacant
lots with "0 <street>" / numberless addresses never resolve, and every land
record Oren opened in '02. Ready to Call' had a blank APN. The Notes
"[Parcel ID: …]" fallback still ships in the upload; this sweep puts the
number in the real field too.

Shape mirrors trestle_api_backfill / text_touch_api_backfill: importable
run_sweep() that upload_netnew_datasift.py calls after every upload,
plus a CLI for by-hand runs.

Scope: every preset in the NSM folder (the folder holding "02. Ready to
Call"). Candidates = records whose street is blank, "0 "-prefixed, or
numberless (DataSift enrich can't resolve those). A candidate is patched
only when ALL of:
  * its live parcel_id/apn is blank (never overwrite),
  * the pipeline's post-collapse *_datasift.csv canonical index has a parcel
    for that street+zip (the Parcel ID column there is the chosen MAIN parcel
    after multi-parcel collapse — never the raw scrape files, which carry one
    row per sibling lot),
  * the record's owner surname appears in that row's decedent name
    (same-street stranger guard).
Every write is verified by re-GET (never search — the index lags writes).

Preset stored queries live under the `filters` key of GET
/api/internal/filter-preset/{uuid}/ and can carry UI-only tokens the raw
API rejects: property_type "all" and relative dates ("72-months", "month",
"quarter"). translate_query() converts both before replication.

Usage:
    python apn_backfill_step.py            # report only
    python apn_backfill_step.py --apply    # patch
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from trestle_api_backfill import API, get_token, headers, _search  # noqa: E402

logger = logging.getLogger("apn_backfill")

ANCHOR_PRESET = "02. Ready to Call"   # defines the NSM folder
RESULT_CSV = REPO / "output" / "apn_backfill_last_run.csv"


def norm_street(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^0\s+", "", s)
    s = re.sub(r"[.,#]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def clean_parcel(p: str) -> str:
    return re.sub(r"\.0+$", "", (p or "").strip())


def _rel_date(tok: str) -> str:
    m = re.match(r"^(\d+)-months?$", tok or "")
    months = int(m.group(1)) if m else {"month": 1, "quarter": 3,
                                        "year": 12}.get(tok, 0)
    days = int(months * 30.44) if months else (7 if tok == "week" else 0)
    return (date.today() - timedelta(days=days)).isoformat()


def translate_query(query: dict) -> dict:
    """Convert a stored preset filter's UI-only tokens into API-valid values."""
    q = json.loads(json.dumps(query or {}))
    must = q.get("must") or {}
    if must.get("property_type") in ("all", None):
        must["property_type"] = "clean"
    if isinstance(must.get("last_direct_mailed"), list):
        a, b = must["last_direct_mailed"]
        must["last_direct_mailed"] = [_rel_date(a), _rel_date(b)]
    for ent in must.get("last_updated_date") or []:
        opts = ent.get("options")
        if isinstance(opts, list) and len(opts) == 2:
            ent["options"] = [_rel_date(opts[0]) + "T00:00:00Z",
                              _rel_date(opts[1]) + "T23:59:59Z"]
    q["must"] = must
    return q


def unresolvable_street(street: str) -> bool:
    """Streets DataSift's address-based enrich can't resolve a parcel for."""
    s = (street or "").strip()
    return (not s or s.lower() == "no address" or s.startswith("0 ")
            or s == "0" or not s[0].isdigit())


def nsm_preset_queries(h: dict) -> list[tuple[str, dict]]:
    r = requests.get(f"{API}/api/internal/filter-preset/", headers=h,
                     params={"limit": 200}, timeout=30)
    r.raise_for_status()
    presets = r.json().get("results") or r.json().get("data") or []
    folder = None
    for p in presets:
        if ANCHOR_PRESET.lower() in (p.get("title") or "").lower():
            f = p.get("folder")
            folder = (f.get("uuid") or f.get("id")) if isinstance(f, dict) else f
            break
    if folder is None:
        logger.warning("anchor preset %r not found — no sweep", ANCHOR_PRESET)
        return []
    out = []
    for p in presets:
        f = p.get("folder")
        fid = (f.get("uuid") or f.get("id")) if isinstance(f, dict) else f
        if fid != folder:
            continue
        det = requests.get(
            f"{API}/api/internal/filter-preset/{p.get('uuid') or p.get('id')}/",
            headers=h, timeout=30)
        body = det.json() if det.status_code == 200 else p
        stored = body.get("filters") or body.get("query") or body.get("filter")
        if stored:
            out.append((p.get("title") or "?", translate_query(stored)))
    return sorted(out)


def build_canonical() -> dict[tuple[str, str], dict]:
    """street+zip -> {parcel, case, decedent, src} from the post-collapse
    *_datasift.csv weeklies. Latest file wins."""
    canon: dict[tuple[str, str], dict] = {}
    for f in sorted(REPO.glob("output/**/*datasift*.csv"),
                    key=lambda f: f.stat().st_mtime):
        try:
            with open(f, newline="", encoding="utf-8-sig", errors="replace") as fh:
                rd = csv.DictReader(fh)
                cols = rd.fieldnames or []
                pcol = next((c for c in cols
                             if c.strip().lower() == "parcel id"), None)
                acol = next((c for c in cols if c.strip().lower()
                             in ("property address", "property street")), None)
                zcol = next((c for c in cols if c.strip().lower()
                             in ("property zip", "property zip code")), None)
                ccol = next((c for c in cols if c.strip().lower()
                             in ("case no.", "case no")), None)
                dcol = next((c for c in cols if c.strip().lower()
                             in ("decedent", "decedent name")), None)
                if not (pcol and acol):
                    continue
                for row in rd:
                    parcel = clean_parcel(row.get(pcol) or "")
                    if not parcel:
                        continue
                    key = (norm_street(row.get(acol) or ""),
                           (row.get(zcol) or "").strip()[:5] if zcol else "")
                    prev = canon.get(key) or {}
                    case = (row.get(ccol) or "").strip() if ccol else ""
                    dec = (row.get(dcol) or "").strip() if dcol else ""
                    # newer file wins the parcel, but a row with no decedent /
                    # case column must not blank out identity fields the
                    # surname gate needs (Francis 26E000455-540, 2026-08-26)
                    canon[key] = {
                        "parcel": parcel, "src": f.name,
                        "case": case or prev.get("case", ""),
                        "decedent": dec or prev.get("decedent", ""),
                    }
        except Exception:
            continue
    return canon


def run_sweep(*, apply: bool = False) -> int:
    h = headers(get_token())
    queries = nsm_preset_queries(h)
    if not queries:
        return 1

    candidates: dict[str, dict] = {}
    for name, q in queries:
        rows = _search(h, q)
        n_cand = 0
        for row in rows:
            street = ((row.get("address") or {}).get("street") or "")
            if unresolvable_street(street):
                candidates.setdefault(row.get("uuid"), row)
                n_cand += 1
        logger.info("  %s: %d records, %d unresolvable-address", name,
                    len(rows), n_cand)
    logger.info("APN sweep: %d unique candidate record(s)", len(candidates))
    if not candidates:
        return 0

    canon = build_canonical()
    plan, skipped = [], []
    for uuid in candidates:
        g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                         timeout=30)
        if g.status_code != 200:
            skipped.append((uuid, f"GET {g.status_code}"))
            continue
        d = g.json()
        if str(d.get("parcel_id") or d.get("apn") or "").strip():
            continue   # already has one
        a = d.get("address") or {}
        ow = d.get("owner") or {}
        street = (a.get("street") or "").strip()
        zp = str(a.get("postal_code") or "")[:5]
        hit = canon.get((norm_street(street), zp))
        surname = (ow.get("last_name") or "").strip().lower()
        label = f"{street}, {a.get('city') or ''} {zp}"
        if not hit:
            skipped.append((label, "no parcel in local weeklies"))
            continue
        if not (surname and surname in (hit.get("decedent") or "").lower()):
            skipped.append((label, f"surname gate: owner {surname!r} vs "
                                   f"decedent {hit.get('decedent')!r} "
                                   f"(candidate {hit['parcel']})"))
            continue
        plan.append({"uuid": uuid, "label": label, "parcel": hit["parcel"],
                     "case": hit["case"], "src": hit["src"]})

    for label, why in skipped:
        logger.info("  skip %s — %s", label, why)
    if not plan:
        logger.info("APN sweep: nothing to patch "
                    "(%d skipped)", len(skipped))
        return 0

    logger.info("APN sweep: %d record(s) to patch%s", len(plan),
                "" if apply else " (report-only; use --apply)")
    ok = fail = 0
    for r in plan:
        logger.info("  %s | %s -> %s", r["label"], r["case"] or "(no case)",
                    r["parcel"])
        if not apply:
            continue
        pr = requests.patch(f"{API}/api/internal/property/{r['uuid']}/",
                            headers=h,
                            data=json.dumps({"parcel_id": r["parcel"],
                                             "apn": r["parcel"]}),
                            timeout=30)
        if pr.status_code not in (200, 202):
            logger.warning("  PATCH %s -> %s %s", r["label"], pr.status_code,
                           pr.text[:150])
            fail += 1
            continue
        chk = requests.get(f"{API}/api/internal/property/{r['uuid']}/",
                           headers=h, timeout=30)
        got = str((chk.json() if chk.status_code == 200 else {})
                  .get("parcel_id") or "").strip()
        if got == r["parcel"]:
            ok += 1
        else:
            logger.warning("  VERIFY MISMATCH %s: wrote %r read back %r",
                           r["label"], r["parcel"], got)
            fail += 1
    if apply:
        logger.info("APN sweep done: %d patched+verified, %d failed, "
                    "%d skipped", ok, fail, len(skipped))
        try:
            with open(RESULT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(plan[0].keys()))
                w.writeheader()
                w.writerows(plan)
        except OSError:
            pass
    return 0 if not fail else 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the patches (default: report only)")
    args = ap.parse_args()
    return run_sweep(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
