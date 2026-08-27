"""2026-08-26 FIX: stamp missing APNs on land records across the NSM flow.

Phase A (read-only): replicate the 3 presets whose stored queries 400'd
(00. Needs Skipped, 07. Mail Monthly, 11. Not Interested - Qtrly) by
translating the UI's relative-date tokens to real dates, union any records
not already covered, per-record GET, and surface additional land records
with a blank parcel. New finds are resolved against the post-collapse
*_datasift.csv canonical index with an owner-surname sanity gate.

Phase B (writes): for every target with a verified parcel, PATCH
{"parcel_id": P, "apn": P} (Kluttz fix_kluttz_parcel_20260817 pattern).
Guards: never overwrite a non-empty parcel; owner surname must still match
the plan row at patch time; verify every write by re-GET (never search —
the search index lags writes).

Run:  d:\SiftStack\.venv\Scripts\python.exe d:\SiftStack\apn_gap_fix_20260826.py
      (add --dry-run to skip Phase B writes)
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from apn_gap_scout_20260826 import API, OUT, get_token, headers

DRY = "--dry-run" in sys.argv
TODAY = date.today()


def norm_street(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^0\s+", "", s)
    s = re.sub(r"[.,#]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def clean_parcel(p: str) -> str:
    return re.sub(r"\.0+$", "", (p or "").strip())


def rel_date(tok: str) -> str:
    """'72-months' -> date 72 months back; 'month' -> 1 month back;
    'quarter' -> 3 months back."""
    m = re.match(r"^(\d+)-months?$", tok or "")
    months = int(m.group(1)) if m else {"month": 1, "quarter": 3,
                                        "week": 0, "year": 12}.get(tok, 0)
    days = int(months * 30.44) if months else (7 if tok == "week" else 0)
    return (TODAY - timedelta(days=days)).isoformat()


def translate_query(query: dict) -> dict:
    q = json.loads(json.dumps(query))  # deep copy
    must = q.get("must") or {}
    if must.get("property_type") in ("all", None):
        must["property_type"] = "clean"
    if isinstance(must.get("last_direct_mailed"), list):
        a, b = must["last_direct_mailed"]
        must["last_direct_mailed"] = [rel_date(a), rel_date(b)]
    for ent in must.get("last_updated_date") or []:
        opts = ent.get("options")
        if isinstance(opts, list) and len(opts) == 2:
            ent["options"] = [rel_date(opts[0]) + "T00:00:00Z",
                              rel_date(opts[1]) + "T23:59:59Z"]
    q["must"] = must
    return q


def fetch_records(h: dict, query: dict) -> list[dict]:
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset, "query": query},
                          timeout=60)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    return out


def build_canonical() -> dict[tuple[str, str], dict]:
    canon: dict[tuple[str, str], dict] = {}
    for f in sorted(REPO.glob("output/**/*datasift*.csv"),
                    key=lambda f: f.stat().st_mtime):
        try:
            with open(f, newline="", encoding="utf-8-sig", errors="replace") as fh:
                rd = csv.DictReader(fh)
                cols = rd.fieldnames or []
                pcol = next((c for c in cols if c.strip().lower() == "parcel id"), None)
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
                    canon[key] = {
                        "parcel": parcel, "src": f.name,
                        "case": (row.get(ccol) or "").strip() if ccol else "",
                        "decedent": (row.get(dcol) or "").strip() if dcol else "",
                    }
        except Exception:
            continue
    return canon


def main() -> int:
    h = headers(get_token())

    # ---------- Phase A: the 3 un-replicated presets ----------
    known_uuids = {r.get("uuid") for r in json.loads(
        (OUT / "records_union.json").read_text(encoding="utf-8"))}
    presets = json.loads((OUT / "presets_all.json").read_text(encoding="utf-8"))
    extra: dict[str, list[str]] = {}
    for p in presets:
        name = p.get("title") or p.get("name") or ""
        if not any(name.startswith(k) for k in ("00.", "07.", "11.")):
            continue
        uuid = p.get("uuid") or p.get("id")
        det = requests.get(f"{API}/api/internal/filter-preset/{uuid}/",
                           headers=h, timeout=30).json()
        query = translate_query(det.get("filters") or det.get("query") or {})
        try:
            recs = fetch_records(h, query)
        except requests.HTTPError as e:
            print(f"!! {name}: still failing ({e}) — needs manual eyes")
            continue
        fresh = [r for r in recs if r.get("uuid") not in known_uuids]
        print(f"{name}: {len(recs)} records ({len(fresh)} not in earlier union)")
        for r in fresh:
            extra.setdefault(r["uuid"], []).append(name)

    new_land_missing = []
    if extra:
        def one(u):
            r = requests.get(f"{API}/api/internal/property/{u}/", headers=h,
                             timeout=30)
            return r.json() if r.status_code == 200 else {"uuid": u, "_error": 1}
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            fulls = list(ex.map(one, list(extra)))
        for rec in fulls:
            if rec.get("_error"):
                continue
            st_type = (rec.get("structure_type") or "").lower()
            street = ((rec.get("address") or {}).get("street") or "").strip()
            if not (any(k in st_type for k in ("vacant", "land", "lot"))
                    or street.startswith("0 ")):
                continue
            if str(rec.get("parcel_id") or rec.get("apn") or "").strip():
                continue
            new_land_missing.append(rec)
        print(f"NEW land records missing APN from these presets: "
              f"{len(new_land_missing)}")

    # ---------- assemble the patch plan ----------
    with open(OUT / "apn_patch_plan.csv", newline="", encoding="utf-8-sig") as fh:
        plan = [{"uuid": r["uuid"], "street": r["street"], "city": r["city"],
                 "zip": r["zip"], "owner": r["owner"],
                 "parcel": clean_parcel(r["final_parcel"]),
                 "case": r["final_case"], "src": r["final_src"]}
                for r in csv.DictReader(fh)]

    canon = build_canonical()
    unresolved = []
    for rec in new_land_missing:
        a = rec.get("address") or {}
        ow = rec.get("owner") or {}
        street, zp = (a.get("street") or "").strip(), \
            str(a.get("postal_code") or "")[:5]
        owner = " ".join(x for x in [ow.get("first_name"),
                                     ow.get("last_name")] if x)
        hit = canon.get((norm_street(street), zp))
        surname = (ow.get("last_name") or "").strip().lower()
        if hit and surname and surname in (hit.get("decedent") or "").lower():
            plan.append({"uuid": rec["uuid"], "street": street,
                         "city": a.get("city") or "", "zip": zp,
                         "owner": owner, "parcel": hit["parcel"],
                         "case": hit["case"], "src": hit["src"]})
        else:
            unresolved.append(f"{street}, {a.get('city')} {zp} | {owner} | "
                              f"{'candidate ' + hit['parcel'] + ' failed surname gate' if hit else 'no local match'}")

    print(f"\nPATCH PLAN — {len(plan)} records:")
    for r in plan:
        print(f"  {r['street']}, {r['city']} {r['zip']} | {r['owner']} | "
              f"{r['case'] or '(no case)'} -> {r['parcel']}")
    if unresolved:
        print("UNRESOLVED (not patched):")
        for u in unresolved:
            print(f"  {u}")
    if DRY:
        print("\n--dry-run: no writes.")
        return 0

    # ---------- Phase B: PATCH + verify ----------
    ok = fail = 0
    for r in plan:
        g = requests.get(f"{API}/api/internal/property/{r['uuid']}/",
                         headers=h, timeout=30)
        if g.status_code != 200:
            print(f"  !! GET {r['street']} -> {g.status_code}; skipped")
            fail += 1
            continue
        d = g.json()
        live_parcel = str(d.get("parcel_id") or d.get("apn") or "").strip()
        live_last = ((d.get("owner") or {}).get("last_name") or "").strip().lower()
        plan_last = r["owner"].split()[-1].lower() if r["owner"] else ""
        if live_parcel:
            print(f"  == {r['street']}: already has parcel {live_parcel!r}; skipped")
            continue
        if plan_last and live_last != plan_last:
            print(f"  !! {r['street']}: owner changed ({live_last!r} != "
                  f"{plan_last!r}); skipped")
            fail += 1
            continue
        pr = requests.patch(f"{API}/api/internal/property/{r['uuid']}/",
                            headers=h,
                            data=json.dumps({"parcel_id": r["parcel"],
                                             "apn": r["parcel"]}),
                            timeout=30)
        if pr.status_code not in (200, 202):
            print(f"  !! PATCH {r['street']} -> {pr.status_code} "
                  f"{pr.text[:150]}")
            fail += 1
            continue
        chk = requests.get(f"{API}/api/internal/property/{r['uuid']}/",
                           headers=h, timeout=30).json()
        got = str(chk.get("parcel_id") or "").strip()
        if got == r["parcel"]:
            print(f"  OK {r['street']} -> {got}")
            ok += 1
        else:
            print(f"  !! VERIFY MISMATCH {r['street']}: wrote {r['parcel']!r} "
                  f"read back {got!r}")
            fail += 1

    print(f"\nDONE: {ok} patched+verified, {fail} failed/skipped, "
          f"{len(unresolved)} unresolved")
    with open(OUT / "apn_patch_result.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(plan[0].keys()))
        w.writeheader()
        w.writerows(plan)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
