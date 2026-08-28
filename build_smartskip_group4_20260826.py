"""Backup-heir phones -> Group-1-format push file (Oren's call, 2026-08-26).

These 242 numbers belong to RELATIVES - sons, daughters, siblings, in-laws - not
to the person named on the record. Oren asked for them on the record anyway so
callers see them without opening a spreadsheet. That is safe only because every
phone carries a label naming whose number it is, e.g.

    ["Dial First", "Jane Doe (Child, at property)", "SmartSkip"]

Nothing is renamed and nothing is blanked: the pusher deep-copies the owner and
appends. The owner-unchanged assertion in the verify step still holds.

Order matters. Phones are emitted closest-relative-first (the review file is
already ranked that way), so if a record hits the per-record phone cap it is the
most distant cousin that gets dropped, never the spouse.

Out: output/smartskip_group4_backup_heir_phones.json
Run (Oren - the classifier blocks Claude's DataSift writes):
    .venv\\Scripts\\python.exe push_smartskip_group1_20260825.py \\
        --src output/smartskip_group4_backup_heir_phones.json \\
        --tag "SmartSkip Heirs 2026-08" --dry-run
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict, OrderedDict
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))

from build_smartskip_group3_20260826 import latest_pr_by_case  # noqa: E402

BACKUP = REPO / "output" / "smartskip_group3_backup_heirs.csv"
OUT = REPO / "output" / "smartskip_group4_backup_heir_phones.json"

PUSH_TIERS = {"Dial First", "Dial Second"}

# find_record() matches a record when its owner is the court PR OR the
# "Heirs <decedent>" placeholder. On estates where the court has named nobody,
# pr_last would be "" - and an empty string would match any record carrying a
# BLANK surname. This sentinel can never equal a real surname, so those estates
# can only ever match through the Heirs branch, which is the correct one.
NO_PR_SENTINEL = "__no_court_pr__"


def main() -> int:
    with BACKUP.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    by_case: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in rows:
        by_case.setdefault((r.get("Case No.") or "").strip(), []).append(r)

    prs = latest_pr_by_case()
    entries = []
    people_used = 0
    skipped_nophone = 0

    for case, heirs in by_case.items():
        src = prs.get(case) or {}
        pr_name = (src.get("Personal Representative") or "").strip()
        has_pr = bool(pr_name) and not pr_name.lower().startswith("heirs of")

        decedent = (heirs[0].get("Deceased Owner") or "").strip()
        prop = (heirs[0].get("Property Address") or "").strip()
        county = (heirs[0].get("County") or "").strip()
        if not prop:
            continue

        phones = []
        for h in heirs:
            name = (h.get("Heir Name") or "").strip()
            rel = (h.get("Relationship") or "").strip() or "relative"
            at_prop = (h.get("At Property") or "").strip().upper() == "YES"
            got = []
            for slot in ("Phone 1", "Phone 2"):
                num = (h.get(slot) or "").strip()
                tier = (h.get(f"{slot} Tier") or "").strip()
                if num and tier in PUSH_TIERS:
                    got.append((num, tier))
            if not got:
                skipped_nophone += 1
                continue
            # "at property" rides in the label because it changes how the
            # caller treats the person: call yes, mail no.
            label = f"{name} ({rel}{', at property' if at_prop else ''})"
            for num, tier in got:
                phones.append({"phone": num, "tier": tier,
                               "line_type": "", "label": label})
            people_used += 1

        if not phones:
            continue

        entries.append({
            "case_no": case, "county": county, "decedent": decedent,
            "property": prop,
            "court_pr": pr_name if has_pr else f"Heirs of {decedent}",
            "pr_first": pr_name.split()[0] if has_pr and pr_name.split() else "",
            "pr_last": (pr_name.replace(",", " ").split()[-1]
                        if has_pr and pr_name.split() else NO_PR_SENTINEL),
            "matched_name": "", "relationship": "backup heirs",
            "phones": phones,
        })

    OUT.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    print(f"estates            : {len(entries)}")
    print(f"backup heirs used  : {people_used}")
    print(f"skipped (no phone) : {skipped_nophone}")
    print(f"phones queued      : {sum(len(e['phones']) for e in entries)}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
