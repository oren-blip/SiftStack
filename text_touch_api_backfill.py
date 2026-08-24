"""Text-touch backfill that reads records from the DataSift API, not an export.

WHY THIS EXISTS
---------------
`text_touch_step.py` only writes Text Touch 1-4 for ONE upload batch, and only
when that night's chain got all the way there:

    upload -> skip trace STARTED -> tier step returned 0 -> text touches

Anything that puts a record into "02. Ready to Call" by another door never got
touches at all:

  * a night where the skip trace didn't start, or the tier step failed — the
    touch call is nested inside `if rc == 0`, so it is skipped silently
  * DP pushes / manual_corrections renames — the record HAD touches, but they
    were written while the owner still read "Heirs of X", so the drafts carry
    the wrong name (or the no-name phrasing on a record that now has a real
    heir on it)
  * bulk record repairs (the 8/14 "Incomplete" batch), hand-entered rows, and
    anything uploaded before this step shipped (2026-07-28)
  * the Phone Enrichment export the step sources from is a SUBSET view — the
    same blindness that made `trestle_backfill_step.py` report all-clear while
    20 phones sat untiered (see trestle_api_backfill.py)

So this is the text-touch twin of `trestle_api_backfill.py`: same scope (the
RTC preset Oren actually looks at + the last N days of upload batches), read
over the API so it cannot be blind, and written with a per-record custom-field
PATCH instead of an Add Data upsert — no address matching, so no duplicate risk
on Oren's hand-entered rows.

Two defects it repairs:
  MISSING — one or more of Text Touch 1-4 is blank/absent
  DRIFT   — the stored draft doesn't match what the record's CURRENT owner and
            address would render (the DP-rename case)

Default run is a FREE AUDIT (no writes).

    python text_touch_api_backfill.py                  # audit NSM 02-05 + last 7 days
    python text_touch_api_backfill.py --apply          # fix missing + drifted
    python text_touch_api_backfill.py --apply --missing-only
    python text_touch_api_backfill.py --preset "02. Ready to Call" --apply
    python text_touch_api_backfill.py --preset "" --tag "NC Upload 2026-08-22" --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from trestle_api_backfill import collect_scope, headers  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("touch_backfill")

API = "https://apiv2.reisift.io"
TOUCH_LABELS = [f"Text Touch {i}" for i in range(1, 5)]
TOKEN_CACHE = REPO / "output" / ".ds_token.json"
GENERATOR = REPO / ".claude/skills/text-touch-builder/scripts/build_text_touches.py"


# The skill generator is imported (not shelled out to) so the API record can
# feed render() directly. Same pools + same seeding => a record that is already
# correct regenerates byte-identical text, which is what makes DRIFT meaningful.
def _load_generator():
    spec = importlib.util.spec_from_file_location("build_text_touches", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GEN = _load_generator()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


# ── auth: cached token first, browser login last (it is the flaky part) ──
def token_works(tok: str) -> bool:
    try:
        return requests.get(f"{API}/api/internal/custom-fields/?entity_type=property",
                            headers=headers(tok), timeout=20).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _browser_login() -> str | None:
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            t = await page.evaluate("() => localStorage.getItem('rs_token')") if ok else None
            await b.close()
            return t
    return asyncio.run(go())


def get_token() -> str:
    for env in ("DS_TOKEN", "DATASIFT_TOKEN"):
        t = (os.environ.get(env) or "").strip().strip('"')
        if t and token_works(t):
            logger.info("auth: using %s from the environment", env)
            return t
    if TOKEN_CACHE.exists():
        try:
            cached = json.loads(TOKEN_CACHE.read_text(encoding="utf-8")).get("token", "")
            if cached and token_works(cached):
                logger.info("auth: reusing cached token (no browser login needed)")
                return cached
        except (OSError, ValueError):
            pass
    for attempt in range(1, 4):
        logger.info("auth: browser login attempt %d/3 ...", attempt)
        t = _browser_login()
        if t and token_works(t):
            TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_CACHE.write_text(json.dumps({"token": t}), encoding="utf-8")
            logger.info("auth: logged in, token cached")
            return t
        if attempt < 3:
            time.sleep(20)
    raise RuntimeError("DataSift login failed")


# ── custom fields ──
def touch_field_uuids(h: dict) -> dict[str, str]:
    r = requests.get(f"{API}/api/internal/custom-fields/", headers=h,
                     params={"entity_type": "property", "limit": 500}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"custom-fields list HTTP {r.status_code}")
    js = r.json()
    rows = js if isinstance(js, list) else (js.get("results") or js.get("data") or [])
    out = {}
    for f in rows:
        lab = (f.get("label") or "").strip()
        if lab in TOUCH_LABELS:
            out[lab] = f.get("uuid") or f.get("field_uuid") or f.get("id")
    return out


def get_cf_values(h: dict, uuid: str) -> dict[str, str]:
    r = requests.get(f"{API}/api/internal/property/{uuid}/custom-field/",
                     headers=h, params={"offset": 0, "limit": 1000}, timeout=30)
    if r.status_code != 200:
        return {}
    out = {}
    for e in (r.json().get("results") or []):
        lab = ((e.get("custom_field") or {}).get("label") or "").strip()
        if lab:
            out[lab] = _norm(e.get("value") or "")
    return out


def write_touches(h: dict, uuid: str, fields: dict[str, str],
                  touches: list[str]) -> bool:
    """PATCH all four, then re-GET to prove it landed (a silent no-op = failure)."""
    body = [{"field_uuid": fields[lab], "value": t}
            for lab, t in zip(TOUCH_LABELS, touches)]
    r = requests.patch(f"{API}/api/internal/property/{uuid}/custom-field/update-values/",
                       headers=h, data=json.dumps(body), timeout=30)
    if r.status_code not in (200, 202):
        logger.warning("  PATCH %s -> %s %s", uuid[:8], r.status_code, r.text[:150])
        return False
    back = get_cf_values(h, uuid)
    for lab, t in zip(TOUCH_LABELS, touches):
        if back.get(lab, "") != _norm(t):
            logger.warning("  verify failed on %s for %s (reads %r)",
                           lab, uuid[:8], back.get(lab, "")[:60])
            return False
    return True


# ── rendering from the live record ──
def _assigned_first(prop: dict) -> str:
    a = prop.get("assigned_to") or prop.get("assignee") or {}
    if isinstance(a, dict):
        name = " ".join(x for x in [a.get("first_name") or "",
                                    a.get("last_name") or ""] if x).strip()
        name = name or (a.get("name") or a.get("full_name") or "")
    else:
        name = str(a or "")
    return GEN.clean_first(name)


# Records carrying this tag get the vacant/absentee copy instead of the general
# pools: different opener (drive-by, not "is this yours"), and the copy is
# guarded against ever naming the distress. See build_text_touches.VACANT_POOLS.
VACANT_TAG = "priority 1"


def record_niche(prop: dict) -> str:
    """'vacant' when the record carries the Priority 1 tag, else 'default'."""
    for t in (prop.get("tags") or []):
        name = t.get("title") or t.get("name") if isinstance(t, dict) else t
        if (name or "").strip().lower() == VACANT_TAG:
            return "vacant"
    return "default"


def expected_touches(prop: dict, sender_default: str):
    """The four drafts this record's CURRENT owner + address should carry.

    Mirrors build_text_touches.main() exactly, sourced from the API record
    instead of the CSV export. Returns (touches, meta) or None when the record
    is not renderable (no street, or nothing to sign with).

    Pool set is chosen per record by record_niche() — the vacant stack gets
    VACANT_POOLS, everything else keeps the general-purpose copy.
    """
    addr = prop.get("address") or {}
    if not isinstance(addr, dict):
        return None
    street = _norm(addr.get("street") or "")
    if not street:
        return None                              # Incomplete record — nothing to say
    city = _norm(addr.get("city") or "")
    owner = prop.get("owner") or {}
    raw_first = _norm(owner.get("first_name") or "")
    owner_full = _norm(raw_first + " " + _norm(owner.get("last_name") or ""))
    no_name = bool(GEN.ENTITY_RX.search(owner_full or raw_first))
    first = "" if no_name else GEN.clean_first(raw_first)
    sender = _assigned_first(prop) or sender_default.strip().title()
    if not sender:
        return None
    niche = record_niche(prop)
    touches = GEN.render((street + "|" + owner_full).lower(), first,
                         GEN.tidy_addr(street), GEN.tidy_place(city) or "the area",
                         sender, no_name,
                         pools=GEN.POOLS_BY_NICHE.get(niche))
    if any(len(t) > GEN.MAX_CHARS for t in touches):
        return None
    return touches, {"street": street, "owner": owner_full, "first": first,
                     "sender": sender, "niche": niche}


# Every NSM stage a caller dials from. Sweeping only "02. Ready to Call" left a
# hole: a record that advances to Follow-Up 1-3 leaves RTC, so a DP rename after
# that point never got its drafts refreshed and the caller greeted the wrong
# person on attempt 2+. The 8/23 audit found 19 such records across 03/04/05.
NSM_CALL_STAGES = ["02. Ready to Call", "03. Follow-Up 1",
                   "04. Follow-Up 2", "05. Follow-Up 3"]


def run_sweep(*, preset: str | list[str] | None = None,
              tags: list[str] | None = None, recent_days: int = 7,
              apply: bool = False, missing_only: bool = False,
              sender: str = "Oren", limit: int = 0) -> int:
    """Audit (and optionally repair) text touches. Importable by the nightly.

    `preset` takes one name or a list of them; None means NSM_CALL_STAGES.
    Pass "" (or an empty list) to skip presets and sweep tags only.
    """
    h = headers(get_token())
    try:
        fields = touch_field_uuids(h)
    except RuntimeError as e:
        logger.error("%s", e)
        return 2
    missing_defs = [lab for lab in TOUCH_LABELS if lab not in fields]
    if missing_defs:
        logger.error("Custom field(s) not found: %s — run text_touch_step.py once "
                     "to create them.", ", ".join(missing_defs))
        return 2

    if preset is None:
        presets = list(NSM_CALL_STAGES)
    elif isinstance(preset, str):
        presets = [preset] if preset else []
    else:
        presets = [p for p in preset if p]

    # One collect_scope per preset, unioned. Records sitting in two stages are
    # read once; `origin` is only for the log line.
    pool: dict[str, dict] = {}
    origin: dict[str, list[str]] = {}
    for name in presets:
        for u, rec in collect_scope(h, name, [], 0).items():
            pool.setdefault(u, rec)
            origin.setdefault(u, []).append(name)
    if tags or recent_days > 0:
        for u, rec in collect_scope(h, None, list(tags or []), recent_days).items():
            pool.setdefault(u, rec)
            origin.setdefault(u, []).append("batch tag")
    logger.info("Scope: %d unique record(s) across %d preset(s)%s",
                len(pool), len(presets),
                " + batch tags" if (tags or recent_days > 0) else "")
    if not pool:
        logger.info("Nothing in scope.")
        return 0

    todo, skipped, ok = [], [], 0
    uuids = list(pool)[:limit] if limit else list(pool)
    for i, ru in enumerate(uuids, 1):
        if i % 25 == 0:
            logger.info("  ...read %d/%d records", i, len(uuids))
        fr = requests.get(f"{API}/api/internal/property/{ru}/", headers=h, timeout=30)
        if fr.status_code != 200:
            logger.warning("  record %s -> HTTP %s", ru[:8], fr.status_code)
            continue
        js = fr.json()
        prop = js.get("data") or js
        exp = expected_touches(prop, sender)
        if exp is None:
            addr = prop.get("address") or {}
            skipped.append(((addr.get("street") if isinstance(addr, dict) else "")
                            or "(no address)", "not renderable"))
            continue
        touches, meta = exp
        cur = get_cf_values(h, ru)
        blanks = [lab for lab in TOUCH_LABELS if not cur.get(lab)]
        drifted = [lab for lab, t in zip(TOUCH_LABELS, touches)
                   if cur.get(lab) and cur[lab] != _norm(t)]
        if blanks:
            kind = "MISSING"
        elif drifted:
            kind = "DRIFT"
        else:
            ok += 1
            continue
        rec = {"uuid": ru, "kind": kind, "touches": touches,
               "blanks": len(blanks), "drifted": len(drifted),
               "stages": ";".join(origin.get(ru, [])),
               "current_t1": cur.get("Text Touch 1", "")}
        rec.update(meta)
        todo.append(rec)

    n_missing = sum(1 for t in todo if t["kind"] == "MISSING")
    n_drift = sum(1 for t in todo if t["kind"] == "DRIFT")
    out = REPO / "output" / f"text_touch_backfill_{datetime.now():%Y%m%d_%H%M}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Defect", "Property Address", "Owner", "Signer", "Niche", "Stage",
                    "Blank fields", "Drifted fields", "Stored Touch 1", "New Touch 1",
                    "Record UUID"])
        for t in todo:
            w.writerow([t["kind"], t["street"], t["owner"], t["sender"],
                        t.get("niche", ""), t.get("stages", ""), t["blanks"],
                        t["drifted"], t["current_t1"], t["touches"][0], t["uuid"]])

    logger.info("Text touches: %d record(s) OK, %d MISSING, %d DRIFT, %d not "
                "renderable", ok, n_missing, n_drift, len(skipped))
    for t in todo:
        detail = (f"{t['blanks']} blank" if t["kind"] == "MISSING"
                  else f"{t['drifted']} drifted (owner now {t['owner']!r})")
        logger.info("   %-8s %-34s %s", t["kind"], t["street"][:34], detail)
    if skipped:
        logger.info("   not renderable: %s", skipped[:5])
    logger.info("Audit CSV: %s", out)

    targets = [t for t in todo
               if t["kind"] == "MISSING" or (not missing_only and t["kind"] == "DRIFT")]
    if not targets:
        logger.info("Nothing to write — every record in scope carries current drafts.")
        return 0
    if not apply:
        logger.info("Audit only (no writes). Re-run with --apply to write %d record(s).",
                    len(targets))
        return 0

    wrote, failed = 0, 0
    for t in targets:
        if write_touches(h, t["uuid"], fields, t["touches"]):
            wrote += 1
            logger.info("   wrote %s (%s)", t["street"], t["kind"])
        else:
            failed += 1
    logger.info("Wrote touches on %d record(s); %d failed.", wrote, failed)
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", action="append", default=None,
                    help="filter preset to audit; repeatable. Default is every "
                         "NSM call stage (%s). Pass '' to skip presets."
                         % ", ".join(NSM_CALL_STAGES))
    ap.add_argument("--tag", action="append", default=[],
                    help="extra batch tag to audit (repeatable)")
    ap.add_argument("--recent-days", type=int, default=7,
                    help="also audit 'NC Upload YYYY-MM-DD' tags for the last N "
                         "days (default 7; 0 disables)")
    ap.add_argument("--apply", action="store_true",
                    help="write the repairs (default: free audit, no writes)")
    ap.add_argument("--missing-only", action="store_true",
                    help="only fill blank fields; leave drifted drafts alone")
    ap.add_argument("--sender", default="Oren",
                    help="first name signing the texts when the record has no assignee")
    ap.add_argument("--limit", type=int, default=0, help="cap records read (debug)")
    args = ap.parse_args()
    return run_sweep(preset=args.preset, tags=args.tag, recent_days=args.recent_days,
                     apply=args.apply, missing_only=args.missing_only,
                     sender=args.sender, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
