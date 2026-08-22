"""READ-ONLY audit: which DP'd cases are still owned by "Heirs ..." in DataSift?

Prompted by Punch 26E000919-170 (2026-08-22): the record read "DP Complete"
while the owner was still "Heirs Punch", because the 8/14 sweep pushed that
estate's PHONES (dp_phones_20260814.csv) but left it out of the DM CSV
(dp_dm_20260814.csv), and the 8/19 push then filed it under TAG_ONLY. Oren
said "here is ANOTHER one", so this checks the whole queue for the same gap.

Writes NOTHING. Every call is a GET / search. Safe to run any time.

    cd d:\\SiftStack
    python audit_rename_gap_20260822.py

Method
  1. Every case in manual_corrections.csv with a First/Last Name correction
     is a queued rename off "Heirs <Decedent>".
  2. Case No. -> property address comes from the FTM *_datasift.csv exports.
  3. Each record is located in DataSift by street search (surname fallback),
     then reported as PUSHED (owner renamed) / GAP (still "Heirs") /
     NOT FOUND / AMBIGUOUS.

Output: output/rename_gap_audit_20260822.csv + a console summary.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as _dt
import glob
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")
API = "https://apiv2.reisift.io"

OUT = REPO / "output" / "rename_gap_audit_20260822.csv"
_LOG = open(REPO / "logs" / "audit_rename_gap_20260822.log", "a", encoding="utf-8")
_w = sys.stdout.write
sys.stdout.write = lambda t: (_w(t), _LOG.write(t), _LOG.flush())[0]
print(f"\n===== read-only audit at {_dt.datetime.now()} =====")


def queued_renames() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    p = REPO / "manual_corrections.csv"
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 3:
                continue
            case, field, val = row[0].strip(), row[1].strip().lower(), row[2].strip()
            if field in ("first name", "last name"):
                out.setdefault(case, {})[field] = val
    return out


def case_addresses() -> dict[str, tuple[str, str]]:
    """Case No. -> (street, city), latest file wins.

    Source is the FTM pipeline CSVs ("Case No." + "Property Address"), NOT the
    *_datasift.csv upload exports — those drop the case number, which is what
    made the first run of this audit report 29 false NOT FOUNDs.
    """
    m: dict[str, tuple[str, str]] = {}
    files = sorted(glob.glob(str(REPO / "output" / "nc_estates_ftm_*.csv")),
                   key=os.path.getmtime)
    used = 0
    for f in files:
        try:
            with open(f, encoding="utf-8-sig", newline="") as fh:
                r = csv.DictReader(fh)
                flds = r.fieldnames or []
                ck = next((c for c in flds if c.strip().lower() in
                           ("case no.", "case no", "case number")), None)
                sk = next((c for c in flds if c.strip().lower() in
                           ("property address", "property street address")), None)
                if not ck or not sk:
                    continue
                used += 1
                for row in r:
                    c = (row.get(ck) or "").strip()
                    street = (row.get(sk) or "").strip()
                    if c and street:
                        m[c] = (street, (row.get("Property City") or "").strip())
        except Exception as e:  # noqa: BLE001
            print(f"  (skipping {os.path.basename(f)}: {e})")
    print(f"case->address map: {len(m)} cases from {used} CSVs")
    return m


def token() -> str | None:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        print("using DS_TOKEN from environment")
        return t
    try:
        from get_ds_token import get_token
        t = get_token()
        if t:
            return t
        print("no working token in Chrome storage — Playwright login fallback")
    except Exception as e:  # noqa: BLE001
        print(f"Chrome token harvest failed ({e}) — Playwright login fallback")
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            t = (await page.evaluate("() => localStorage.getItem('rs_token')")
                 if ok else None)
            await b.close()
            return t
    return asyncio.run(go())


def search(h: dict, text: str) -> list[dict]:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      data=json.dumps({"query": {"must": {"search": text}},
                                       "limit": 200}), timeout=30)
    if r.status_code != 200:
        return []
    d = r.json()
    return d.get("results") or d.get("data") or []


def main() -> int:
    ren = queued_renames()
    addrs = case_addresses()
    print(f"queued renames in manual_corrections.csv: {len(ren)}")

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    rows, gaps = [], []
    for case in sorted(ren):
        want_fn = ren[case].get("first name", "")
        want_ln = ren[case].get("last name", "")
        street, city = addrs.get(case, ("", ""))
        rec, note = None, ""

        # DataSift's search is unreliable on street text ("994 22nd St Pl NE"
        # returns 0 while the record reads "994 22Nd Street Pl Ne"), so a
        # surname search + house-number filter is the workhorse, not the
        # fallback. House number is the disambiguator in both branches.
        num = (street.split() or [""])[0].lower() if street else ""
        for q in ([street] if street else []) + ([want_ln] if want_ln else []):
            hits = search(h, q)
            if len(hits) == 1:
                rec = hits[0]
                break
            if len(hits) > 1:
                exact = hits
                if num:
                    exact = [x for x in exact
                             if ((x.get("address") or {}).get("street") or "")
                             .lower().startswith(num + " ")]
                if len(exact) > 1 and want_ln:
                    byname = [x for x in exact
                              if ((x.get("owner") or {}).get("last_name") or "")
                              .strip().lower() == want_ln.strip().lower()]
                    if byname:
                        exact = byname
                if len(exact) == 1:
                    rec = exact[0]
                    break
                note = f"{len(hits)} hits on {q!r} ({len(exact)} after filter)"

        if rec is None:
            status, live = "NOT FOUND", ""
        else:
            o = rec.get("owner") or {}
            live = f"{(o.get('first_name') or '').strip()} {(o.get('last_name') or '').strip()}".strip()
            first = (o.get("first_name") or "").strip().lower()
            # "Heirs", "Heirs Of", "Estate Of" are all the un-renamed placeholder
            if first.startswith(("heirs", "heir", "estate")):
                status = "GAP"
            elif first == want_fn.strip().lower():
                status = "PUSHED"
            else:
                status = "OTHER NAME"
        tags = [t.get("title") if isinstance(t, dict) else str(t)
                for t in ((rec or {}).get("tags") or [])]
        dp_done = any("dp complete" in t.lower() for t in tags)
        uuid = (rec or {}).get("uuid") or (rec or {}).get("id") or ""

        print(f"  {case:20s} {status:10s} live={live!r:28s} want={want_fn} {want_ln}"
              f"{'  [DP Complete]' if dp_done else ''}{'  ' + note if note else ''}")
        rows.append({"Case No.": case, "Status": status, "Live Owner": live,
                     "Wanted Owner": f"{want_fn} {want_ln}".strip(),
                     "DP Complete tag": "yes" if dp_done else "no",
                     "Property": f"{street}, {city}".strip(", "),
                     "UUID": uuid, "Note": note})
        if status == "GAP":
            gaps.append((case, live, f"{want_fn} {want_ln}".strip(), uuid, dp_done))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["Case No."])
        wtr.writeheader()
        wtr.writerows(rows)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["Status"]] = counts.get(r["Status"], 0) + 1
    print(f"\n==== SUMMARY ====")
    for k in sorted(counts):
        print(f"  {k:12s} {counts[k]}")
    if gaps:
        print(f"\nSTILL 'Heirs' IN DATASIFT ({len(gaps)}) — same bug as Punch:")
        for case, live, want, uuid, dp in gaps:
            print(f"  {case:20s} {live!r} -> should be {want!r}"
                  f"{'  (tagged DP Complete)' if dp else ''}  {uuid}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
