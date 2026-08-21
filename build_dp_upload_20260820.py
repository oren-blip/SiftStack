"""Build the DataSift upload CSV for the heirs-sweep cases that were never
uploaded (Oren approved 2026-08-20: "upload new").

Sources: output/dp_heirs_sweep_20260820/results.json (the research) + the
archived weekly pick CSVs (the FTM rows, already patched with DM columns).

Included:  resolved cases NOT in the upload ledger, weeks <= 33, DM off-site.
Excluded:  week 34 (tonight's nightly auto-upload carries the current week —
           uploading them here too would race it), DM-at-property cases
           (occupied-hold candidates, not marketing leads — listed at the end
           for Oren), and anything already in the ledger / manual archive.

Contact = the verified DM (owner fields), mailing = DM's own address.
Personal Representative stays "Heirs of <decedent>" (the court truth) but the
"Needs DP" tag is swapped for "DP Complete" — these ARE deep-prospected.
Phones = every Trestle score >= 21, best first; litigator numbers are NOT
uploaded at all (a CSV can't phone-tag them "Litigator - DNC", so keeping
them out is the only safe TCPA route).

Then (AFTER the nightly is fully down):
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\upload_netnew_datasift.py ^
        --csv output/dp_heirs_upload_20260820_NETNEW.csv --list PROBATE --no-skip-trace
(--no-skip-trace: these rows already carry Enformion phones — don't pay
DataSift to re-trace. The post-upload Trestle tier sweep hits today's score
cache, so Dial tags cost ~$0.)
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
import os

os.chdir(REPO)

from nc_datasift_export import (  # noqa: E402
    DATASIFT_UPLOAD_COLUMNS, NEEDS_DP_TAG, _row_to_datasift,
    load_upload_ledger,
)
from consolidate_weeks import auto_pick_weekly_files  # noqa: E402
from dp_push_heirs_20260820 import parse_full_address, tier  # noqa: E402

OUT_CSV = REPO / "output" / "dp_heirs_upload_20260820_NETNEW.csv"
CURRENT_WEEK = 34

results = json.loads((REPO / "output" / "dp_heirs_sweep_20260820" / "results.json")
                     .read_text(encoding="utf-8"))
resolved = {e["case_no"].upper(): e for e in results if e.get("outcome") == "resolved"}
ledger = load_upload_ledger()

# FTM rows for every resolved case, from the archived pick files
picks = auto_pick_weekly_files(include_archived=True)
ftm_rows: dict[str, tuple[dict, int]] = {}
for (yr, wk), path in sorted(picks.items()):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cn = (r.get("Case No.") or "").strip().upper()
            if cn in resolved and cn not in ftm_rows:
                ftm_rows[cn] = (r, wk)

upload_rows: list[tuple[dict, int, str]] = []   # (ftm row, week, case_no)
skipped_occupied: list[str] = []
skipped_other: list[str] = []
for cn, e in sorted(resolved.items()):
    if cn in ledger:
        continue  # already in DataSift — dp_push_heirs handles those
    row_wk = ftm_rows.get(cn)
    if not row_wk:
        skipped_other.append(f"{cn} (no FTM row found in pick files)")
        continue
    r, wk = row_wk
    if wk >= CURRENT_WEEK:
        continue  # tonight's nightly auto-upload carries the current week
    dm = e["dm"]
    if dm["occupied_flag"]:
        skipped_occupied.append(
            f"{cn} {e['county']}: {dm['matched_name']} ({dm['relationship']}) "
            f"lives AT {e['property']}")
        continue

    r = dict(r)  # never mutate the pick data
    # Promote the verified DM to the contact slots
    r["First Name"] = dm["first"]
    r["Last Name"] = dm["last"]
    r["DM Name"] = f"{dm['first']} {dm['last']}"
    r["DM Relationship"] = dm["relationship"]
    parsed = parse_full_address(dm.get("address") or "")
    if parsed and all(parsed.values()):
        r["Mailing Address"] = parsed["street"]
        r["Mailing City"] = parsed["city"]
        r["Mailing State"] = parsed["state"]
        r["Mailing Zip"] = parsed["postal_code"]
    note = (r.get("Notes") or "").strip()
    dp_note = (f"[DP 2026-08-20: {dm['matched_name']} ({dm['relationship']}) "
               "verified via Enformion relatives graph; court has no appointed PR]")
    if dp_note not in note:
        r["Notes"] = (note + ("\n" if note else "") + dp_note).strip()
    upload_rows.append((r, wk, cn))

# Render through the standard converter, then fix phones + tags per row
final: list[dict] = []
for r, wk, cn in upload_rows:
    tags = f"Courthouse Data,NC Estates Week {wk} 2026"
    out = _row_to_datasift(r, tags, trace_tag=None)
    e = resolved[cn]
    phones = [s["phone"] for s in sorted((e.get("scored") or []),
                                         key=lambda s: -(s.get("score") or 0))
              if not s.get("litigator") and (s.get("score") or 0) >= 21]
    for i in range(1, 10):
        out[f"Phone {i}"] = phones[i - 1] if i <= len(phones) else ""
    # The FTM Tags column uses " | " separators (ecourts-backfill marker etc.)
    # — split on both so no compound tag reaches DataSift.
    tag_list = [t.strip() for t in re.split(r"[,|]", out["Tags"])
                if t.strip() and t.strip() != NEEDS_DP_TAG]
    tag_list.append("DP Complete")
    out["Tags"] = ",".join(dict.fromkeys(tag_list))
    final.append(out)

OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=DATASIFT_UPLOAD_COLUMNS, extrasaction="ignore")
    w.writeheader()
    w.writerows(final)
# Sidecar so upload_netnew_datasift.py appends these to the upload ledger
with OUT_CSV.with_suffix(".cases.json").open("w", encoding="utf-8") as f:
    json.dump({"cases": sorted(cn for _, _, cn in upload_rows)}, f, indent=1)

n_phones = sum(1 for o in final for i in range(1, 10) if o[f"Phone {i}"])
print(f"upload rows: {len(final)} ({n_phones} phones) -> {OUT_CSV}")
print(f"\nEXCLUDED — occupied (hold candidates, {len(skipped_occupied)}):")
for s in skipped_occupied:
    print("  " + s)
if skipped_other:
    print(f"\nEXCLUDED — other ({len(skipped_other)}):")
    for s in skipped_other:
        print("  " + s)
wk34 = [cn for cn, e in resolved.items()
        if cn not in ledger and ftm_rows.get(cn) and ftm_rows[cn][1] >= CURRENT_WEEK]
print(f"\nLeft to tonight's nightly auto-upload (week {CURRENT_WEEK}): {len(wk34)}")
