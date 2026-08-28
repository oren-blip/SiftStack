"""Batch 3 upload: SmartSkip the "Needs DP" queue, court-first and dedupe-first.

Queue audit 2026-08-27 (read-only, tag search + address rejoin): 31 records
tagged "Needs DP". This file covers the 26 that map to a case number.
  - 26E000782-480 excluded: resolved 8/20, the tag is stale.
  - 5 address-only records (no case in any weekly file) are HELD for review,
    not traced: 2923 Shady Ln Charlotte (Meck, paused), 1175 Briarwood Dr
    Walnut Cove (Stokes - outside the 7 counties), 127 Ellis Rd Gastonia,
    7800 Nine Iron Ct Denver, 4558 N Wynswept Dr Maiden.

Flow, per the 8/27 go-ahead:
  1. FREE pass - the freshest weekly view (fed by the nightly Parties backfill)
     already names a court PR for some cases. Those are reported, not traced:
     DataSift's unlimited skip trace is the $0 next step for a named PR.
  2. The rest become decedent-subject SmartSkip rows.
  3. The export has NO already-traced guard (measured 8/24), so this script
     drops any case OR SiftKey present in a prior batch keymap - a subject
     must never be paid for twice.
  4. The banked batch-3 PR seed (5 rows, built earlier 8/27) is merged into
     the final upload file, as that script intended.

Writes files only. Nothing is uploaded anywhere by this script.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import smartskip_io as ss  # noqa: E402
from build_smartskip_group3_20260826 import latest_pr_by_case  # noqa: E402

# The 26 case-mapped "Needs DP" records, DataSift tag audit 2026-08-27 20:01.
QUEUE_CASES = [
    "26E000806-790",  # Bryan / 110 Stratford Pl, Pineville (Rowan case)
    "26E000782-480",  # Hall / 3028 Jennings Rd, Olin — STALE, resolved 8/20
    "26E001066-350",  # Scotto / 404 Mountain Meadows Dr, Bessemer City
    "26E000508-540",  # Ingle / 1026 Guy Heavner Rd, Lincolnton
    "26E000834-790",  # Bean / 1880 Needmore Rd, Woodleaf
    "26E001093-350",  # Mack / 2226 Donnabrook Ln, Gastonia
    "26E001111-350",  # Bradley / 1272 Dorchester Rd, Gastonia
    "26E000826-480",  # Jolly / 1060 Tomlin Mill Rd, Statesville
    "26E001116-350",  # Vaughn / 5220 Featherstone Ct, Gastonia
    "26E000874-120",  # Schenck / 258 Blackberry Trl, Concord
    "26E000830-480",  # Haynes / 471 Jane Sowers Rd, Statesville
    "26E001126-350",  # Mcmillen / 916 Jupiter St, Gastonia
    "26E000982-170",  # Beach / 1117 Shiloh Rd, Claremont
    "26E000880-120",  # Vonhall / 4928 Copper Creek Trl, Kannapolis
    "26E000873-790",  # Anderton / 120 Random Dr, Salisbury
    "26E000994-170",  # Bentley / 2602 2nd Ave NW, Hickory
    "26E000533-540",  # Vandall / 4197 Kent St, Maiden
    "26E000886-790",  # Dennis / 109 W Vance St, China Grove
    "26E001142-350",  # Rouse / 236 Charlotte St, Alexis
    "26E000537-540",  # Lynn / 8555 Old NC 18 Rd, Vale
    "26E001140-350",  # Wright / 927 Summer Dr, Gastonia
    "26E001141-350",  # Lowery / Eighth Ave, Cramerton
    "26E001146-350",  # Mcclure / 2324 Linwood Rd, Gastonia
    "26E000888-790",  # Smith / 285 Aviation Dr, Kannapolis
    "26E001145-350",  # Brooks / 632 Morningside Dr, Mount Holly
    "26E000844-480",  # Privott / 755 N Main St, Mooresville
]
STALE = {"26E000782-480"}

PRIOR_KEYMAPS = [
    REPO / "output" / "smartskip_upload_20260824_215620_keymap.csv",
    REPO / "output" / "smartskip_upload_20260826_keymap.csv",
    REPO / "output" / "smartskip_upload_20260826_noMeck_keymap.csv",
]
SEED = REPO / "output" / "smartskip_batch3_pr_seed_20260827.csv"
SEED_KEYMAP = REPO / "output" / "smartskip_batch3_pr_seed_20260827_keymap.csv"

OUT = REPO / "output" / "smartskip_upload_20260827_batch3.csv"


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> int:
    paid_cases: set[str] = set()
    paid_keys: set[str] = set()
    for km in PRIOR_KEYMAPS:
        if not km.exists():
            continue
        for r in _read(km):
            paid_cases.add((r.get("Case No.") or "").strip())
            paid_keys.add((r.get(ss.KEY_COLUMN) or "").strip())
    paid_cases.discard("")
    paid_keys.discard("")

    prs = latest_pr_by_case()

    court_named: list[tuple[str, str, str]] = []   # case, PR, decedent
    to_trace: list[dict] = []
    already_paid: list[str] = []
    missing: list[str] = []

    for case in QUEUE_CASES:
        if case in STALE:
            continue
        if case in paid_cases:
            already_paid.append(case)
            continue
        row = prs.get(case)
        if row is None:
            missing.append(case)
            continue
        pr = (row.get("Personal Representative") or "").strip()
        dec = (row.get("Deceased Owner") or "").strip()
        if pr and not pr.lower().startswith("heirs of"):
            court_named.append((case, pr, dec))
        else:
            to_trace.append(row)

    written, skipped, keymap_path = ss.build_upload_csv(to_trace, OUT)

    # Cross-batch SiftKey guard: same decedent traced before under another case.
    new_rows = [r for r in _read(OUT)
                if (r.get(ss.KEY_COLUMN) or "").strip() not in paid_keys]
    key_dropped = written - len(new_rows)
    new_keymap = [r for r in _read(keymap_path)
                  if (r.get(ss.KEY_COLUMN) or "").strip() not in paid_keys]

    # Merge the banked PR seed (already formatted by the same builder).
    seed_rows = _read(SEED) if SEED.exists() else []
    seed_keymap = _read(SEED_KEYMAP) if SEED_KEYMAP.exists() else []

    cols = ss.UPLOAD_COLUMNS + [ss.KEY_COLUMN]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(new_rows + seed_rows)
    km_cols = [ss.KEY_COLUMN, "County", "Case No.", "Parcel ID",
               "Deceased Owner", "Property Address"]
    with keymap_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=km_cols, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(new_keymap + seed_keymap)

    total = len(new_rows) + len(seed_rows)
    print(f"\n=== {OUT.name} ===")
    print(f"decedent subjects written : {len(new_rows)} "
          f"(builder skipped {skipped}, prior-key dropped {key_dropped})")
    print(f"banked PR-seed rows merged: {len(seed_rows)}")
    print(f"TOTAL rows / cost         : {total} / ${total * ss.COST_PER_ROW:.2f}")
    print(f"keymap: {keymap_path.name}")

    if court_named:
        print(f"\nCOURT ANSWERED ({len(court_named)}) - no trace needed, "
              f"PR is named in the case file; DataSift trace is the free next step:")
        for case, pr, dec in court_named:
            print(f"  {case}: PR {pr}  (estate of {dec})")
    if already_paid:
        print(f"\nALREADY TRACED in a prior batch ({len(already_paid)}) - "
              f"re-check those ingest results instead of re-buying:")
        for case in already_paid:
            print(f"  {case}")
    if missing:
        print(f"\nNOT IN WEEKLY FILES ({len(missing)}) - need a hand look:")
        for case in missing:
            print(f"  {case}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
