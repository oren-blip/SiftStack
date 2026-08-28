"""Build the phones JSON for the "Needs DP" queue push - heir phones, no renames.

Source: the three ingest review CSVs (8/24, 8/26, 8/27). Covers the 19 queue
cases whose SmartSkip results were paid for but never pushed onto the records:
16 from the earlier batches plus the 3 resolved by tonight's batch 3
(McClure 26E001146-350, Brooks 26E001145-350, Privott 26E000844-480).

None of these cases has a court PR (all owners read "Heirs X"), so this is a
PHONES-ONLY push in the group-4 backup-heir shape: per-phone label carries the
heir's name + relationship so a caller sees whose number it is before dialling.
pr_last is set to the decedent's surname so find_record's owner guard accepts
the "Heirs <surname>" record (or a same-surname rename) and nothing else.

Writes output/smartskip_queue_heir_phones_20260827.json. Pushes NOTHING.
Review via:
  python push_smartskip_group1_20260825.py --src output/smartskip_queue_heir_phones_20260827.json --tag "SmartSkip Heirs Queue 2026-08" --dry-run
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

REPO = Path(r"d:\SiftStack")
OUT = REPO / "output" / "smartskip_queue_heir_phones_20260827.json"

REVIEWS = [
    REPO / "output" / "smartskip_heirs_20260824_scored.csv",
    REPO / "output" / "smartskip_heirs_20260826_scored.csv",
    REPO / "output" / "smartskip_heirs_20260827_213346.csv",
]

CASES = [
    "26E001066-350", "26E000508-540", "26E000834-790", "26E001093-350",
    "26E001111-350", "26E000826-480", "26E001116-350", "26E000874-120",
    "26E000830-480", "26E001126-350", "26E000982-170", "26E000880-120",
    "26E000873-790", "26E000994-170", "26E000533-540", "26E001142-350",
    "26E001140-350",
    "26E001146-350", "26E000888-790", "26E001145-350", "26E000844-480",
]

PUSH_TIERS = {"Dial First", "Dial Second"}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def decedent_last(name: str) -> str:
    """Surname of 'Last, First ...' or 'First ... Last[, Suffix]'."""
    name = (name or "").strip()
    if "," in name:
        head, tail = (p.strip() for p in name.split(",", 1))
        tail_toks = [t.rstrip(".").lower() for t in tail.split()]
        if tail_toks and all(t in _SUFFIXES for t in tail_toks):
            # "John Henry Smith, Jr" — First-Last format with a suffix tail.
            toks = [t for t in head.split()
                    if t.rstrip(".").lower() not in _SUFFIXES]
            return toks[-1].lower() if toks else ""
        return head.lower()          # "McClure, Doris Allman" — Last, First
    toks = [t for t in name.split() if t.rstrip(".").lower() not in _SUFFIXES]
    return toks[-1].lower() if toks else ""


def main() -> int:
    by_case: dict[str, dict] = {}
    for path in REVIEWS:
        if not path.exists():
            print(f"missing review file: {path.name}")
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                case = (r.get("Case No.") or "").strip()
                if case not in CASES:
                    continue
                dec = (r.get("Deceased Owner") or "").strip()
                e = by_case.setdefault(case, {
                    "case_no": case,
                    "county": (r.get("County") or "").strip(),
                    "decedent": dec,
                    "property": (r.get("Property Address") or "").strip(),
                    "court_pr": "",
                    "pr_first": "",
                    "pr_last": decedent_last(dec),
                    "matched_name": "",
                    "relationship": "queue heirs",
                    "phones": [],
                })
                heir = (r.get("Heir Name") or "").strip()
                rel = (r.get("Relationship") or "").strip() or "Relative"
                at_prop = (r.get("At Property") or "").strip().upper() == "YES"
                label = f"{heir} ({rel}{', at property' if at_prop else ''})"
                for pcol, tcol in (("Phone 1", "Phone 1 Tier"),
                                   ("Phone 2", "Phone 2 Tier")):
                    num = (r.get(pcol) or "").strip()
                    tier = (r.get(tcol) or "").strip()
                    if num and tier in PUSH_TIERS:
                        e["phones"].append({"phone": num, "tier": tier,
                                            "line_type": "", "label": label})

    entries = [e for e in by_case.values() if e["phones"]]
    empty = [c for c in CASES if c not in by_case or not by_case[c]["phones"]]

    OUT.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    n_phones = sum(len(e["phones"]) for e in entries)
    print(f"wrote {OUT.name}: {len(entries)} estate(s), {n_phones} phone(s) "
          f"(pre-dedupe; the push dedupes against the record and caps at 15)")
    for e in sorted(entries, key=lambda x: x["case_no"]):
        print(f"  {e['case_no']:15} {e['decedent'][:28]:28} {len(e['phones'])} phone(s)")
    if empty:
        print(f"no pushable phones for: {', '.join(empty)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
