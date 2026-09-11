"""Merge the two private-money-lender sources into one master sheet.

  1. Pace Morby's PML lists (Subto community, shared into Drive 2026-09-09) -
     WARM. Every row has a name, an email, a phone and a check size. These
     lenders already fund community members' deals and expect the call.
  2. The Facebook group harvest (fb_lender_harvest.py) - COLD, but current:
     these people were posting about funding deals this month.

Anyone appearing in BOTH is the top of the list: a lender who is in Pace's
community AND actively hunting deals in public right now.

    python merge_lender_lists.py
    python merge_lender_lists.py --fb output/fb_private_lenders_2026-09-10.csv

Writes output/private_lenders_master_<date>.csv. Nothing is uploaded anywhere.
"""
from __future__ import annotations

import argparse
import csv
import glob
import re
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
TODAY = datetime.now().strftime("%Y-%m-%d")

SUFFIX_RE = re.compile(r"\b(llc|l\.l\.c|inc|corp|co|ltd|lp|llp|group|capital|holdings?)\b\.?", re.I)


def norm_phone(v: str) -> str:
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else ""


def norm_email(v: str) -> str:
    v = str(v or "").strip().lower()
    m = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", v)
    return m.group(0) if m else ""


def norm_name(v: str) -> str:
    v = SUFFIX_RE.sub(" ", str(v or "").lower())
    v = re.sub(r"[^a-z ]+", " ", v)
    return " ".join(v.split())


def money(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(",", "").replace("+", "").strip())
    except Exception:
        return 0.0


def load_pace() -> list[dict]:
    rows = []
    for f in sorted(glob.glob(str(OUT / "pace_pml" / "*.xlsx"))):
        listname = Path(f).stem.replace("PML_List_", "PML #").replace("_", " ")
        wb = openpyxl.load_workbook(f, read_only=True)
        ws = wb.worksheets[0]
        data = list(ws.iter_rows(values_only=True))
        wb.close()
        try:
            hdr = next(i for i, r in enumerate(data)
                       if r and any(str(c).strip().upper() == "NAME" for c in r if c))
        except StopIteration:
            continue
        for r in data[hdr + 1:]:
            if not r or not any(str(c).strip() for c in r if c):
                continue
            name = str(r[0] or "").strip()
            if not name:
                continue
            rows.append({
                "Name": name,
                "Phone": norm_phone(r[2] if len(r) > 2 else ""),
                "Email": norm_email(r[1] if len(r) > 1 else ""),
                "Check size": money(r[3] if len(r) > 3 else 0),
                "List": listname,
            })
    return rows


def load_fb(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(p.open(encoding="utf-8-sig")):
        out.append({
            "Name": r.get("Name", "").strip(),
            "Phone": norm_phone((r.get("Phones") or "").split(",")[0]),
            "Email": norm_email((r.get("Emails") or "").split(",")[0]),
            "Phones": r.get("Phones", ""),
            "Emails": r.get("Emails", ""),
            "Tab": r.get("Tab", ""),
            "Class": r.get("Class", ""),
            "Score": int(r.get("Score") or 0),
            "Evidence": r.get("Evidence", ""),
            "Groups": r.get("Groups", ""),
            "Profile": r.get("Profile", ""),
            "Post": r.get("Post", ""),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fb", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    fb_path = args.fb
    if not fb_path:
        cands = sorted(glob.glob(str(OUT / "fb_private_lenders_*.csv")))
        fb_path = cands[-1] if cands else ""
    pace, fbr = load_pace(), load_fb(fb_path)
    print(f"Pace PML lists: {len(pace)} rows   Facebook harvest: {len(fbr)} rows"
          f"{' (' + Path(fb_path).name + ')' if fb_path else ' (none found)'}")

    # Index Pace by every key it can be matched on.
    by_phone, by_email, by_name = {}, {}, {}
    people: list[dict] = []
    for r in pace:
        rec = {
            "Source": "subto", "In both": "", "Name": r["Name"],
            "Phones": r["Phone"], "Emails": r["Email"],
            "Check size": r["Check size"], "Class": "PACE PML LIST",
            "Where": r["List"], "Score": 0, "Evidence": "", "Profile": "", "Post": "",
        }
        # Same person on several of Pace's lists = one row.
        prior = (by_phone.get(r["Phone"]) if r["Phone"] else None) or \
                (by_email.get(r["Email"]) if r["Email"] else None)
        if prior:
            if r["List"] not in prior["Where"]:
                prior["Where"] += ", " + r["List"]
            prior["Check size"] = max(prior["Check size"], r["Check size"])
            continue
        people.append(rec)
        if r["Phone"]:
            by_phone[r["Phone"]] = rec
        if r["Email"]:
            by_email[r["Email"]] = rec
        if norm_name(r["Name"]):
            by_name.setdefault(norm_name(r["Name"]), rec)

    overlap = 0
    for r in fbr:
        hit = (by_phone.get(r["Phone"]) if r["Phone"] else None) \
            or (by_email.get(r["Email"]) if r["Email"] else None) \
            or (by_name.get(norm_name(r["Name"])) if r["Name"] else None)
        if hit:
            overlap += 1
            hit["In both"] = "YES - on Pace's list AND posting publicly"
            hit["Source"] = "subto + facebook"
            hit["Evidence"] = r["Evidence"]
            hit["Profile"] = r["Profile"] or hit["Profile"]
            hit["Post"] = r["Post"] or hit["Post"]
            hit["Where"] = (hit["Where"] + " | " + r["Groups"]).strip(" |")
            hit["Score"] = max(hit["Score"], r["Score"])
            for k in ("Phones", "Emails"):
                if not hit[k] and r[k]:
                    hit[k] = r[k]
            continue
        people.append({
            "Source": "facebook", "In both": "", "Name": r["Name"],
            "Phones": r["Phones"], "Emails": r["Emails"], "Check size": 0,
            "Class": r["Class"], "Where": r["Groups"], "Score": r["Score"],
            "Evidence": r["Evidence"], "Profile": r["Profile"], "Post": r["Post"],
        })

    def rank(p):
        both = 0 if p["In both"] else 1
        # Pace rows carry a real check size; FB rows carry a confidence score.
        return (both, -p["Check size"], -p["Score"], p["Name"].lower())

    people.sort(key=rank)

    dest = Path(args.out) if args.out else OUT / f"private_lenders_master_{TODAY}.csv"
    cols = ["Source", "In both", "Name", "Phones", "Emails", "Check size",
            "Class", "Where", "Score", "Evidence", "Profile", "Post"]
    with dest.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in people:
            p["Check size"] = f"${int(p['Check size']):,}" if p["Check size"] else ""
            w.writerow(p)

    n_sub = sum(1 for p in people if p["Source"].startswith("subto"))
    n_fb = sum(1 for p in people if p["Source"] == "facebook")
    withph = sum(1 for p in people if p["Phones"])
    withem = sum(1 for p in people if p["Emails"])
    print(f"\n{len(people)} unique lenders")
    print(f"  from Pace's lists   {n_sub}")
    print(f"  from Facebook only  {n_fb}")
    print(f"  on BOTH             {overlap}")
    print(f"  with a phone {withph}   with an email {withem}")
    print(f"\n-> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
