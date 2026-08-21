"""DP heirs sweep 2026-08-20 — Enformion decedent-graph research on every
unworked "Heirs of" case in the FTM workbook (Oren approved 8/20: "go ahead
and do all including Meck").

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_heirs_sweep_20260820.py --dry-run  # list + cost ceiling
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_heirs_sweep_20260820.py            # live

Per case (highest property value first, so early spend goes to the best leads):
  1. Enformion PersonSearch on the DECEDENT anchored to the property
     city/zip — the relativesSummary is the heir graph (2026-08-13 accuracy
     test: a match is trustworthy iff a known family member appears in it).
     Miss + a middle name -> one retry with middle-as-first (court/GIS names
     often lead with the middle name; misses are free).
  2. Rank living relatives: children (18-55 yrs younger) before spouse-aged,
     same surname first. relativeType is usually blank ("Family") so age
     does the classifying.
  3. PersonSearch the top candidate by name + DOB year (no state anchor —
     it misses real people). IDENTITY GATE: the decedent must appear in the
     candidate's own relativesSummary, else try the next candidate (max 2).
  4. Trestle-score all new phones in one batch (litigator suppression on).

READ-ONLY — no DataSift writes (auto-mode classifier blocks them; the push
is staged separately for Oren). Every Enformion response is disk-cached in
output/dp_heirs_sweep_20260820/ so a re-run never re-bills.

Outputs: results.json, output/reports/DP_HeirsSweep_20260820.md,
dp_log.csv appends, manual_corrections.csv appends (resolved cases).
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import openpyxl  # noqa: E402
import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from phone_validator import clean_phone, process_phones  # noqa: E402

DRY = "--dry-run" in sys.argv
_skip = {sys.argv[sys.argv.index("--csv") + 1]} if "--csv" in sys.argv else set()
ONLY = [a for a in sys.argv[1:]
        if not a.startswith("--") and a not in _skip]  # optional case-no filter
OUT = REPO / "output" / "dp_heirs_sweep_20260820"
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = OUT / "results.json"
REPORT = REPO / "output" / "reports" / "DP_HeirsSweep_20260820.md"
DP_LOG = REPO / "dp_log.csv"
CORRECTIONS = REPO / "manual_corrections.csv"

MAX_HEIR_SEARCHES_PER_CASE = 2
MAX_PHONES = 6
COST_PER_MATCH = 0.35  # list-rate ceiling; Starter/challenge rate may be $0.10

HDRS = {
    "galaxy-ap-name": os.environ.get("ENFORMION_AP_NAME", ""),
    "galaxy-ap-password": os.environ.get("ENFORMION_AP_PASSWORD", ""),
    "galaxy-search-type": "Person",
    "content-type": "application/json",
    "accept": "application/json",
}


# ── Enformion plumbing ────────────────────────────────────────────────────

class EnformionAbort(Exception):
    pass


_consec_444 = 0


def person_search(tag: str, body: dict) -> dict:
    """POST PersonSearch, disk-cached by tag. Failure = HTTP status (the
    `error` object is populated on every call). 3 consecutive 444s = the
    geo-block (VPN on) -> abort the whole run."""
    global _consec_444
    f = OUT / f"{tag}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    r = requests.post("https://devapi.enformion.com/PersonSearch",
                      headers=HDRS, json=body, timeout=60)
    if r.status_code == 444:
        _consec_444 += 1
        if _consec_444 >= 3:
            raise EnformionAbort("3 consecutive HTTP 444 — Enformion geo-block. "
                                 "Is the VPN on? Blocked calls use no quota.")
        return {}
    _consec_444 = 0
    if r.status_code in (401, 403):
        raise EnformionAbort(f"HTTP {r.status_code} — auth/quota problem, stopping "
                             "before burning more calls.")
    if r.status_code != 200:
        print(f"    [{tag}] HTTP {r.status_code}: {r.text[:200]}")
        return {}
    data = r.json()
    f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    time.sleep(0.4)
    return data


def year_of(v) -> int:
    if isinstance(v, dict):
        v = " ".join(str(x) for x in v.values())
    m = re.search(r"(19|20)\d{2}", str(v or ""))
    return int(m.group(0)) if m else 0


def is_deceased(p: dict) -> bool:
    v = p.get("isDeceased")
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("true", "yes", "1")


def full_name(p: dict) -> str:
    nm = p.get("name") or {}
    return " ".join(x for x in (nm.get("firstName"), nm.get("middleName"),
                                nm.get("lastName")) if x).strip()


def persons_of(resp: dict) -> list[dict]:
    return [p for p in (resp.get("persons") or resp.get("people") or [])
            if isinstance(p, dict)]


def addr_blob(p: dict) -> str:
    return " ".join((a.get("fullAddress") or "").lower()
                    for a in (p.get("addresses") or []) if isinstance(a, dict))


def extract_phones(p: dict) -> list[str]:
    """Connected mobiles first, deduped, capped."""
    entries = [e for e in (p.get("phoneNumbers") or []) if isinstance(e, dict)]
    entries.sort(key=lambda e: (bool(e.get("isConnected")),
                                "mobile" in str(e.get("phoneType") or "").lower()),
                 reverse=True)
    out, seen = [], set()
    for e in entries:
        digits = "".join(c for c in str(e.get("phoneNumber") or "") if c.isdigit())
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) != 10 or digits in seen or len(out) >= MAX_PHONES:
            continue
        seen.add(digits)
        out.append(digits)
    return out


# ── Name handling ─────────────────────────────────────────────────────────

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "aka"}


def split_decedent(name: str) -> tuple[str, str, str]:
    """'Last, First Middle ...' -> (first, middle, last). Strips AKA tails."""
    s = re.sub(r"\s*,?\s*aka\s+.*$", "", (name or "").strip(), flags=re.I)
    if "," in s:
        last, _, rest = s.partition(",")
        toks = [t for t in rest.split() if t.strip(".").lower() not in _SUFFIXES]
        first = toks[0] if toks else ""
        middle = toks[1] if len(toks) > 1 else ""
        return first.strip("."), middle.strip("."), last.strip()
    toks = [t for t in s.split() if t.strip(".").lower() not in _SUFFIXES]
    if len(toks) >= 2:
        return toks[0].strip("."), " ".join(toks[1:-1]), toks[-1].strip(".")
    return (toks[0] if toks else ""), "", ""


def surname_token(p: dict) -> str:
    nm = p.get("name") or {}
    last = (nm.get("lastName") or "").strip()
    return last.split()[-1].lower() if last else ""


# ── Matching gates ────────────────────────────────────────────────────────

def pick_decedent_match(resp: dict, last: str, city: str, zip5: str,
                        dod_year: int) -> dict | None:
    """Whole-token surname + anchor overlap (property zip/city in address
    history). Prefer deceased candidates and a DOD year that agrees with the
    court filing when we know it."""
    want = (last or "").strip().split()[-1].lower()
    cands = [p for p in persons_of(resp) if surname_token(p) == want]

    def score(p: dict) -> tuple:
        blob = addr_blob(p)
        anchor = (2 if zip5 and zip5 in blob else 0) + \
                 (1 if city and city.lower() in blob else 0)
        dods = p.get("datesOfDeath") or ([p.get("dod")] if p.get("dod") else [])
        dy = year_of(dods[0] if dods else "")
        dod_ok = 1 if (dod_year and dy and abs(dy - dod_year) <= 1) else 0
        return (anchor, dod_ok, 1 if is_deceased(p) else 0)

    cands = [p for p in cands if score(p)[0] > 0]  # anchor overlap required
    if not cands:
        return None
    cands.sort(key=score, reverse=True)
    return cands[0]


def rank_heir_candidates(dec_person: dict) -> list[dict]:
    """Living relatives, children first (18-55 yrs younger), same surname
    first within each class. relativeType is usually blank -> age decides."""
    dec_by = year_of(dec_person.get("dob") or dec_person.get("dateOfBirth"))
    dec_last = surname_token(dec_person)
    rels = [r for r in (dec_person.get("relativesSummary") or [])
            if isinstance(r, dict) and not is_deceased(r)
            and (r.get("firstName") and r.get("lastName"))]

    def klass(r: dict) -> int:
        by = year_of(r.get("dob"))
        if dec_by and by:
            gap = by - dec_by
            if 18 <= gap <= 55:
                return 0  # child-aged
            if abs(gap) <= 12:
                return 1  # spouse/sibling-aged
        return 2

    def key(r: dict):
        same = 0 if (r.get("lastName") or "").split()[-1].lower() == dec_last else 1
        try:
            sc = -float(r.get("score") or 0)
        except (TypeError, ValueError):
            sc = 0
        return (klass(r), same, sc)

    rels.sort(key=key)
    return rels


def identity_gate(heir_person: dict, dec_first: str, dec_last: str) -> bool:
    """The decedent must appear in the heir's own relatives graph."""
    df, dl = dec_first.lower(), dec_last.split()[-1].lower()
    for r in (heir_person.get("relativesSummary") or []):
        if not isinstance(r, dict):
            continue
        rl = (r.get("lastName") or "").split()[-1].lower() if r.get("lastName") else ""
        rf = (r.get("firstName") or "").lower()
        if rl == dl and (rf == df or rf.startswith(df[:3]) if df else False):
            return True
    return False


# ── Load the queue ────────────────────────────────────────────────────────

def load_queue() -> list[dict]:
    # --csv <path>: load rows from a weekly CSV instead of the workbook (for
    # rows whose Case No. was just backfilled and hasn't hit the workbook yet)
    rows = []
    if "--csv" in sys.argv:
        src = Path(sys.argv[sys.argv.index("--csv") + 1])
        with src.open(newline="", encoding="utf-8-sig") as f:
            for d in csv.DictReader(f):
                d["_tab"] = f"Week {re.search(r'week(\d+)', src.name).group(1)} 2026" \
                    if re.search(r"week(\d+)", src.name) else ""
                rows.append(d)
    else:
        wb_path = sorted((REPO / "output").glob("FTM_*_NC_Estates_throughWeek*.xlsx"))[-1]
        wb = openpyxl.load_workbook(wb_path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            hdr = None
            for row in ws.iter_rows(values_only=True):
                if hdr is None:
                    hdr = [str(c or "").strip() for c in row]
                    continue
                d = {h: ("" if v is None else str(v)) for h, v in zip(hdr, row)}
                d["_tab"] = ws.title
                rows.append(d)

    done = set()
    if DP_LOG.exists():
        with DP_LOG.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("Outcome") or "").strip() in ("resolved", "resolved-rejected"):
                    done.add((r.get("Case No.") or "").strip().upper())

    q = []
    for r in rows:
        pr = (r.get("Personal Representative") or "").strip().lower()
        cn = (r.get("Case No.") or "").strip()
        if not pr.startswith("heirs of") or not cn:
            continue
        if cn.upper() in done or (r.get("DM Name") or "").strip():
            continue
        if ONLY and cn not in ONLY:
            continue
        q.append(r)

    def val(r):
        try:
            return float(str(r.get("Property Value") or "").replace("$", "").replace(",", ""))
        except ValueError:
            return 0.0
    q.sort(key=val, reverse=True)
    return q


# ── Main ──────────────────────────────────────────────────────────────────

def wk_of(r: dict) -> int:
    m = re.search(r"Week (\d+)", str(r.get("_tab") or ""))
    return int(m.group(1)) if m else 0


def main() -> int:
    queue = load_queue()
    print(f"Sweep targets: {len(queue)} cases (highest property value first)")
    print(f"Cost ceiling: ~${len(queue) * 3 * COST_PER_MATCH:.0f} at worst "
          f"(3 matches/case list rate) — realistic ~2 matches/case, misses free")
    if DRY:
        for r in queue:
            print(f"  {r.get('Case No.'):18} {r.get('County'):12} "
                  f"{(r.get('Deceased Owner') or '')[:30]:30} "
                  f"${(r.get('Property Value') or '0'):>10}  Wk{wk_of(r)}")
        return 0

    results = []
    if RESULTS.exists():
        results = json.loads(RESULTS.read_text(encoding="utf-8"))
    done_cases = {e["case_no"] for e in results}
    matches_billed = 0

    try:
        for i, r in enumerate(queue, 1):
            cn = (r.get("Case No.") or "").strip()
            if cn in done_cases:
                continue
            county = (r.get("County") or "").strip()
            dec_raw = (r.get("Deceased Owner") or "").strip()
            first, middle, last = split_decedent(dec_raw)
            city = (r.get("Property City") or r.get("Mailing City") or "").strip()
            zip5 = (r.get("Property Zip") or r.get("Mailing Zip") or "").strip()[:5]
            prop = (r.get("Property Address") or "").strip()
            dod_year = year_of(r.get("Date of Death (App)"))
            print(f"\n[{i}/{len(queue)}] {cn} {county} — {dec_raw} "
                  f"({prop}, {city} {zip5})")

            entry = {
                "case_no": cn, "county": county, "week": wk_of(r),
                "decedent": dec_raw, "property": prop,
                "property_city": city, "property_zip": zip5,
                "property_value": r.get("Property Value") or "",
                "outcome": "", "dm": None, "backups": [], "new_phones": [],
                "notes": [],
            }

            # 1. decedent search (retry middle-as-first on miss — free)
            tag = f"{cn}_decedent".replace("/", "-")
            body = {"FirstName": first, "LastName": last,
                    "Addresses": [{"AddressLine2": f"{city}, NC {zip5}".strip()}],
                    "Page": 1, "ResultsPerPage": 10}
            resp = person_search(tag, body)
            dec_match = pick_decedent_match(resp, last, city, zip5, dod_year)
            if dec_match is None and middle:
                resp = person_search(f"{tag}_alt",
                                     {**body, "FirstName": middle})
                dec_match = pick_decedent_match(resp, last, city, zip5, dod_year)
            if dec_match is None:
                entry["outcome"] = "enformion-miss"
                entry["notes"].append("no anchored decedent match")
                print("  MISS — no anchored decedent match")
                results.append(entry)
                RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
                continue
            matches_billed += 1
            print(f"  decedent match: {full_name(dec_match)} "
                  f"b.{year_of(dec_match.get('dob'))} deceased={is_deceased(dec_match)}")

            # 2. rank heirs
            cands = rank_heir_candidates(dec_match)
            if not cands:
                entry["outcome"] = "no-living-relatives"
                entry["notes"].append("decedent matched but relatives graph empty")
                print("  decedent matched, but no living relatives listed")
                results.append(entry)
                RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
                continue
            entry["backups"] = [
                {"name": " ".join(x for x in (c.get("firstName"), c.get("middleName"),
                                              c.get("lastName")) if x),
                 "born": year_of(c.get("dob"))}
                for c in cands[1:3]
            ]

            # 3. heir search with identity gate
            dm = None
            for c in cands[:MAX_HEIR_SEARCHES_PER_CASE]:
                hf, hl = c.get("firstName", ""), c.get("lastName", "")
                hby = year_of(c.get("dob"))
                htag = f"{cn}_heir_{hf}_{hl}".replace("/", "-").replace(" ", "_")
                hbody = {"FirstName": hf, "LastName": hl,
                         "Page": 1, "ResultsPerPage": 5}
                if hby:
                    hbody["Dob"] = str(hby)
                hresp = person_search(htag, hbody)
                for hp in persons_of(hresp):
                    if surname_token(hp) != hl.split()[-1].lower():
                        continue
                    if hby and year_of(hp.get("dob")) and abs(year_of(hp.get("dob")) - hby) > 2:
                        continue
                    if not identity_gate(hp, first, last):
                        continue
                    matches_billed += 1
                    addrs = [a.get("fullAddress") or "" for a in (hp.get("addresses") or [])
                             if isinstance(a, dict)]
                    dec_by = year_of(dec_match.get("dob") or dec_match.get("dateOfBirth"))
                    gap = (year_of(hp.get("dob")) - dec_by) if dec_by and year_of(hp.get("dob")) else 0
                    rel = "Child" if 18 <= gap <= 55 else ("Spouse/Sibling" if abs(gap) <= 12 else "Family")
                    prop_token = re.sub(r"^0\s+", "", prop.lower()).split(",")[0].strip()
                    occupied = bool(prop_token and addrs and prop_token in addrs[0].lower())
                    dm = {"first": hf, "last": hl, "born": year_of(hp.get("dob")),
                          "relationship": rel, "matched_name": full_name(hp),
                          "address": addrs[0] if addrs else "",
                          "occupied_flag": occupied,
                          "phones": extract_phones(hp)}
                    break
                if dm:
                    break

            if not dm:
                entry["outcome"] = "heir-unverified"
                entry["notes"].append(
                    "relatives found but none passed the identity gate: "
                    + ", ".join(f"{c.get('firstName')} {c.get('lastName')}"
                                for c in cands[:3]))
                print("  heirs found but none passed the identity gate")
                results.append(entry)
                RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
                continue

            entry["outcome"] = "resolved"
            entry["dm"] = dm
            entry["new_phones"] = dm["phones"]
            flag = "  ** AT PROPERTY **" if dm["occupied_flag"] else ""
            print(f"  DM: {dm['matched_name']} b.{dm['born']} ({dm['relationship']}) "
                  f"@ {dm['address']}{flag} — {len(dm['phones'])} phone(s)")
            results.append(entry)
            RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")
    except EnformionAbort as e:
        print(f"\n*** ABORTED: {e}")
        print(f"Progress saved — {len(results)} cases in {RESULTS}; re-run to continue.")

    # 4. Trestle scoring — one batch for every resolved case's new phones
    to_score = []
    for e in results:
        if e.get("outcome") == "resolved" and not e.get("scored"):
            for p in e.get("new_phones") or []:
                to_score.append((e["case_no"], clean_phone(p)))
    if to_score:
        print(f"\nTrestle: scoring {len(to_score)} phone(s) "
              f"(~${len(to_score) * 0.015:.2f}), litigator check on")
        scored, errors = process_phones(to_score, os.environ["TRESTLE_API_KEY"],
                                        add_litigator=True)
        by_num = {s.get("phone_number") or s.get("phone"): s for s in scored}
        for e in results:
            if e.get("outcome") != "resolved" or e.get("scored"):
                continue
            e["scored"] = []
            for p in e.get("new_phones") or []:
                c = clean_phone(p)
                s = by_num.get(c, {})
                e["scored"].append({
                    "phone": c, "score": s.get("activity_score"),
                    "line_type": s.get("line_type"),
                    "litigator": s.get("litigator_risk", s.get("is_litigator_risk")),
                })
        for err in errors:
            print("  trestle err:", err)
        RESULTS.write_text(json.dumps(results, indent=1), encoding="utf-8")

    # 5. dp_log + manual_corrections + report
    today = date.today().isoformat()
    logged = set()
    if DP_LOG.exists():
        with DP_LOG.open(newline="", encoding="utf-8-sig") as f:
            logged = {(r.get("Case No.") or "").strip() for r in csv.DictReader(f)
                      if (r.get("Date") or "") == today}
    with DP_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for e in results:
            if e["case_no"] in logged:
                continue
            note = ""
            if e.get("dm"):
                note = (f"DM {e['dm']['matched_name']} ({e['dm']['relationship']})"
                        + (" AT PROPERTY" if e['dm']['occupied_flag'] else ""))
            elif e.get("notes"):
                note = e["notes"][0][:80]
            outcome = "resolved" if e["outcome"] == "resolved" else "partial" \
                if e["outcome"] == "no-living-relatives" else "open"
            w.writerow([today, e["week"], e["case_no"], e["county"],
                        split_decedent(e["decedent"])[2], "L2-enf", outcome,
                        str(REPORT).replace("\\", "/"), note])

    existing_corr = set()
    if CORRECTIONS.exists():
        with CORRECTIONS.open(newline="", encoding="utf-8-sig") as f:
            existing_corr = {((r.get("Case No.") or "").strip(),
                              (r.get("Field") or "").strip())
                             for r in csv.DictReader(f)}
    with CORRECTIONS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for e in results:
            if e.get("outcome") != "resolved":
                continue
            dm = e["dm"]
            best = ""
            for s in sorted(e.get("scored") or [], key=lambda x: -(x.get("score") or 0)):
                if not s.get("litigator") and (s.get("score") or 0) >= 21:
                    best = s["phone"]
                    break
            fields = {
                "DM Name": f"{dm['first']} {dm['last']}",
                "DM Relationship": dm["relationship"],
            }
            if best:
                fields["DM Phone"] = best
            for j, b in enumerate(e.get("backups") or [], 2):
                fields[f"DM {j} Name"] = b["name"]
            for field, value in fields.items():
                if (e["case_no"], field) not in existing_corr:
                    w.writerow([e["case_no"], field, value])

    # report
    by_outcome = Counter(e["outcome"] for e in results)
    lines = [
        "# DP — Heirs-of backlog sweep (Enformion decedent-graph, 2026-08-20)",
        "",
        f"Queue: every unworked \"Heirs of\" case in the workbook (all weeks, "
        f"incl. Mecklenburg — Oren approved 8/20). {len(results)} cases run.",
        "",
        "| Outcome | Cases |", "|---|---|",
    ]
    for k, n in by_outcome.most_common():
        lines.append(f"| {k} | {n} |")
    lines += ["", f"Enformion matches billed this run: ~{matches_billed} "
              f"(${matches_billed * COST_PER_MATCH:.2f} at list rate, "
              f"${matches_billed * 0.10:.2f} at challenge rate)", ""]
    for e in results:
        if e.get("outcome") != "resolved":
            continue
        dm = e["dm"]
        lines.append(f"## {split_decedent(e['decedent'])[2]} {e['case_no']} — "
                     f"{e['property']}, {e['property_city']} ({e['county']})")
        lines.append(f"- Decedent: {e['decedent']} | value ${e['property_value']}")
        lines.append(f"- DM: **{dm['matched_name']}** b.{dm['born']} "
                     f"({dm['relationship']}) @ {dm['address']}"
                     + ("  **AT PROPERTY — hold-review**" if dm["occupied_flag"] else ""))
        if e.get("backups"):
            lines.append("- Backups: " + "; ".join(
                f"{b['name']} b.{b['born']}" for b in e["backups"]))
        for s in e.get("scored") or []:
            tier = ("Litigator - DNC" if s.get("litigator") else
                    "Dial First" if (s.get("score") or 0) >= 81 else
                    "Dial Second" if (s.get("score") or 0) >= 61 else
                    "Dial Third" if (s.get("score") or 0) >= 41 else
                    "Dial Fourth" if (s.get("score") or 0) >= 21 else "Drop")
            lines.append(f"    - {s['phone']}  score {s.get('score')}  "
                         f"{s.get('line_type')}  -> **{tier}**")
        lines.append("")
    unresolved = [e for e in results if e.get("outcome") != "resolved"]
    if unresolved:
        lines.append("## Not resolved (need hand research / obit pass)")
        for e in unresolved:
            lines.append(f"- {e['case_no']} {e['county']} "
                         f"{split_decedent(e['decedent'])[2]}: {e['outcome']}"
                         + (f" — {e['notes'][0]}" if e.get("notes") else ""))
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n===== done: {dict(by_outcome)}")
    print(f"matches billed ~{matches_billed} "
          f"(${matches_billed * COST_PER_MATCH:.2f} list / "
          f"${matches_billed * 0.10:.2f} challenge rate)")
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
