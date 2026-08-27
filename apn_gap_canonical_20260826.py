"""2026-08-26 (read-only): canonical parcel per target from the post-collapse
*_datasift.csv files (FTM upload format — its Parcel ID column is the chosen
MAIN parcel after multi-parcel collapse). Latest file wins. Also dumps the
stored queries of the 3 presets whose replication 400'd, with the error body.

Run:  d:\SiftStack\.venv\Scripts\python.exe d:\SiftStack\apn_gap_canonical_20260826.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from apn_gap_scout_20260826 import API, OUT, get_token, headers


def norm_street(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^0\s+", "", s)
    s = re.sub(r"[.,#]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def clean_parcel(p: str) -> str:
    p = (p or "").strip()
    p = re.sub(r"\.0+$", "", p)   # Excel float artifact "…638.000"
    return p


def main() -> int:
    with open(OUT / "land_missing_apn_resolved.csv", newline="",
              encoding="utf-8-sig") as fh:
        targets = list(csv.DictReader(fh))

    files = sorted(REPO.glob("output/**/*datasift*.csv"),
                   key=lambda f: f.stat().st_mtime)
    canon: dict[tuple[str, str], dict] = {}
    for f in files:
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
                if not (pcol and acol):
                    continue
                for row in rd:
                    parcel = clean_parcel(row.get(pcol) or "")
                    if not parcel:
                        continue
                    key = (norm_street(row.get(acol) or ""),
                           (row.get(zcol) or "").strip()[:5] if zcol else "")
                    canon[key] = {"parcel": parcel, "src": f.name,
                                  "case": (row.get(ccol) or "").strip() if ccol else ""}
        except Exception:
            continue

    print("CANONICAL parcels (latest post-collapse datasift CSV wins):")
    final = []
    for t in targets:
        key = (norm_street(t["street"]), t["zip"])
        hit = canon.get(key)
        parcel = clean_parcel(hit["parcel"] if hit else t["found_parcel"])
        src = hit["src"] if hit else t["source"] + " (raw fallback)"
        case = (hit["case"] if hit else "") or t.get("case_no", "")
        final.append({**t, "final_parcel": parcel, "final_src": src,
                      "final_case": case})
        print(f"  {t['street']}, {t['city']} {t['zip']} | {t['owner']} | "
              f"{case or '(no case)'} -> {parcel}  [{src}]")

    with open(OUT / "apn_patch_plan.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(final[0].keys()))
        w.writeheader()
        w.writerows(final)
    print(f"\nWrote {OUT}\\apn_patch_plan.csv")

    # --- the 3 presets whose stored query 400'd ---
    h = headers(get_token())
    presets = json.loads((OUT / "presets_all.json").read_text(encoding="utf-8"))
    for p in presets:
        name = p.get("title") or p.get("name") or ""
        if not any(k in name for k in ("00.", "07.", "11.")):
            continue
        uuid = p.get("uuid") or p.get("id")
        det = requests.get(f"{API}/api/internal/filter-preset/{uuid}/",
                           headers=h, timeout=30).json()
        query = det.get("query") or det.get("filters") or det.get("filter")
        print(f"\n### {name} stored query:\n{json.dumps(query, indent=1)[:1500]}")
        q = dict(query or {})
        q["property_type"] = "clean"
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 1, "offset": 0, "query": q},
                          timeout=60)
        print(f"replication -> HTTP {r.status_code}: {r.text[:600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
