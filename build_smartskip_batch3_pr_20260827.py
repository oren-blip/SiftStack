"""Batch 3 seed: trace the PR, for the handful of estates where nothing else is left.

Chain of elimination behind this file (2026-08-27):
  92 estates traced -> 25 produced no dialable number
  -> 23 of those returned ONLY the subject row: SmartSkip holds no relatives for
     that decedent, so re-buying the decedent returns the same nothing
  -> 22 resolvable to a case, of which 19 have a court PR with an address anchor
  -> 10 of those 19 ALREADY have phones in DataSift now (nightly Enformion and
     DataSift tracing kept running), 4 are not in DataSift at all
  -> 5 genuinely remain

Subject is the PR at their OWN mailing address (`--subject pr`), NOT the decedent.
That is the narrow case the module supports and the only search left that is
actually different from the one already paid for.

$0.75. Too small to be worth a manual upload on its own - bank it and merge into
the next real batch.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import smartskip_io as ss  # noqa: E402
from build_smartskip_group3_20260826 import latest_pr_by_case  # noqa: E402

# Verified still phone-less in DataSift on 2026-08-27.
CASES = [
    "26E000795-790",   # Martha B. Foster
    "26E000806-790",   # William Sturges Bryan Jr
    "26E000485-540",   # Teddy Allen
    "26E000785-480",   # Karen Black Beck
    "26E000983-170",   # Patricia Dedmon
]

OUT = REPO / "output" / "smartskip_batch3_pr_seed_20260827.csv"


def main() -> int:
    prs = latest_pr_by_case()
    rows = []
    for case in CASES:
        r = prs.get(case)
        if r:
            rows.append(r)
        else:
            print(f"  {case}: not found in weekly files - dropped")

    written, skipped, keymap = ss.build_upload_csv(rows, OUT, subject="pr")
    print(f"wrote {OUT.name}: {written} PR subject(s), {skipped} skipped")
    print(f"keymap: {keymap.name}")
    print(f"cost if uploaded: ${written * ss.COST_PER_ROW:.2f}")

    # A mailing address with no house number is almost always the property
    # address copied in by the polish step, not somewhere the PR actually
    # receives mail - a weak anchor that will probably miss.
    import csv
    with OUT.open(newline="", encoding="utf-8-sig") as f:
        weak = [x for x in csv.DictReader(f)
                if not (x["Mailing Address"] or "").strip()[:1].isdigit()]
    if weak:
        print(f"\nweak anchor (no house number in PR mailing) - {len(weak)}:")
        for x in weak:
            print(f"   {x['First Name']} {x['Last Name']} | "
                  f"{x['Mailing Address']}, {x['Mailing City']} {x['Mailing Zip']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
