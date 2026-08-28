"""Turn the 2026-08-26 SmartSkip review CSV into a Group-1-format push file.

Group 1 (2026-08-25) pushed phones onto the COURT-NAMED PR and renamed nothing,
and it verified clean on all 24 estates. This batch is a different shape - the
subjects were phone-less records, so what came back is a family CLUSTER, not the
PR's own numbers. Most of those relatives are NOT the owner of record.

So this builder emits only the unambiguously safe subset: estates where one of
the returned relatives IS the court's named PR. Those phones belong to the
person already on the record, so appending them renames nothing and guesses
nothing - the exact Group 1 contract, which is why the output feeds the existing
verified pusher via --src rather than a second copy of that code.

Everyone else in the cluster is a BACKUP HEIR. Pushing a sibling's phone onto a
record owned by the PR would attach numbers belonging to someone who is not the
owner, and the standing rule is that the case file wins - so they are counted
and set aside here, never written.

Out: output/smartskip_group3_court_pr_phones.json  (Group 1 format)
     output/smartskip_group3_backup_heirs.csv      (the set-aside remainder)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))

REVIEW = REPO / "output" / "smartskip_heirs_20260826_scored.csv"
OUT_JSON = REPO / "output" / "smartskip_group3_court_pr_phones.json"
OUT_BACKUP = REPO / "output" / "smartskip_group3_backup_heirs.csv"

PUSH_TIERS = {"Dial First", "Dial Second"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_parts(full: str) -> tuple[str, str]:
    """('Derick Estes') -> ('derick', 'estes'); handles 'Estes, Derick'."""
    raw = (full or "").strip()
    if not raw:
        return ("", "")
    if "," in raw:
        head, _, tail = raw.partition(",")
        t = [x for x in tail.split() if x.lower().rstrip(".") not in _SUFFIX]
        if t and len(head.split()) == 1:
            return (norm(t[0]), norm(head))
    toks = [x for x in raw.replace(",", " ").split()
            if x.lower().rstrip(".") not in _SUFFIX]
    if not toks:
        return ("", "")
    if len(toks) == 1:
        return ("", norm(toks[0]))
    return (norm(toks[0]), norm(toks[-1]))


def latest_pr_by_case() -> dict[str, dict]:
    """Case No. -> the most recent weekly view of its PR + decedent.

    Later files win: the eCourts Parties API lags filings, so a case that read
    "Heirs of" in week 29 can have a real court PR by week 35, and that later
    name is the one that must win. Same reason Group 1 refused to rename.
    """
    best: dict[str, tuple] = {}
    for path in sorted(glob.glob(str(REPO / "output" / "*_dm_enriched.csv"))):
        m = re.search(r"(\d{4}-\d{2}-\d{2}).*?week(\d+)", os.path.basename(path))
        if not m:
            continue
        stamp = (m.group(1), int(m.group(2)))
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                case = (r.get("Case No.") or "").strip()
                if not case:
                    continue
                cur = best.get(case)
                if cur is None or stamp >= cur[0]:
                    best[case] = (stamp, r)
    return {c: r for c, (_s, r) in best.items()}


def main() -> int:
    with REVIEW.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_case[(r.get("Case No.") or "").strip()].append(r)

    prs = latest_pr_by_case()

    entries: list[dict] = []
    backup: list[dict] = []
    no_pr = matched = 0

    for case, heirs in sorted(by_case.items()):
        src = prs.get(case) or {}
        pr_name = (src.get("Personal Representative") or "").strip()
        decedent = (heirs[0].get("Deceased Owner") or "").strip()
        prop = (heirs[0].get("Property Address") or "").strip()
        county = (heirs[0].get("County") or "").strip()

        if not pr_name or pr_name.lower().startswith("heirs of"):
            # No court PR to attach to. Renaming from a SmartSkip guess is the
            # exact mistake Group 1 was built to avoid - set aside, never push.
            no_pr += 1
            for h in heirs:
                backup.append({**h, "Why Held": "no court PR named"})
            continue

        pf, pl = name_parts(pr_name)
        hit = None
        for h in heirs:
            hf, hl = name_parts(h.get("Heir Name") or "")
            if hl and hl == pl and hf and pf and (hf == pf
                                                  or hf.startswith(pf[:3])
                                                  or pf.startswith(hf[:3])):
                hit = h
                break

        if not hit:
            for h in heirs:
                backup.append({**h, "Why Held": "not the court PR"})
            continue

        phones = []
        for slot in ("Phone 1", "Phone 2"):
            num = (hit.get(slot) or "").strip()
            tier = (hit.get(f"{slot} Tier") or "").strip()
            if num and tier in PUSH_TIERS:
                phones.append({"phone": num, "tier": tier, "line_type": ""})
        if not phones:
            for h in heirs:
                backup.append({**h, "Why Held": "PR matched but no good phone"})
            continue

        matched += 1
        entries.append({
            "case_no": case, "county": county, "decedent": decedent,
            "property": prop, "court_pr": pr_name,
            "pr_first": pr_name.split()[0] if pr_name.split() else "",
            "pr_last": (pr_name.replace(",", " ").split()[-1]
                        if pr_name.split() else ""),
            "matched_name": hit.get("Heir Name") or "",
            "relationship": hit.get("Relationship") or "",
            "phones": phones,
        })
        # Everyone else on a matched estate is still a backup contact.
        for h in heirs:
            if h is not hit:
                backup.append({**h, "Why Held": "backup heir (PR pushed)"})

    OUT_JSON.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    if backup:
        cols = list(rows[0].keys()) + ["Why Held"]
        with OUT_BACKUP.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_MINIMAL)
            w.writeheader()
            w.writerows(backup)

    print(f"estates in review file      : {len(by_case)}")
    print(f"  court PR matched in cluster: {matched}  -> {OUT_JSON.name}")
    print(f"  no court PR named          : {no_pr}  (never auto-renamed)")
    print(f"  held as backup heirs       : {len(backup)} row(s) -> {OUT_BACKUP.name}")
    print(f"\nphones queued: {sum(len(e['phones']) for e in entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
