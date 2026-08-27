"""Court-mailing sweep for the court-PR-renamed class (Oren approved building 8/26).

Type case: Headen 26E002921-590 — the court-PR correction wave fixed the owner
NAME but deliberately left the mailing at the decedent's property. The court
file has the real PR mailing sitting unused in output/heirs_pr_probe.csv.

Per record (probe Verdict == "PR FOUND", court mailing off-site):
  1. owner["address"] -> the court's PR mailing  (owner.address is the key that
     saves; owner.mailing_address is a silent no-op — see dp_push_mailings)
  2. RENAMED records only: predictivecall_attempts -> 0 and status -> default.
     "Renamed" = the record carries a "PR Corrected" / "PR From Court" /
     "Phones - Other Heir" tag, i.e. the owner name changed AFTER the phones
     were traced, so dials + dispositions were against the old identity.
     Already-named records (owner was the court PR from upload day — Curtis
     Williams 26E000974-350 is the type case) keep calls + status untouched:
     their dispositions were earned with the right person. Oren chose this
     split 8/26 ("Split by renamed", Wilkerson reset with the rest).
  3. tag "Court Mailing Applied"

Guards — any failure skips the record, nothing partial is written:
  * court mailing parses to street/city/state/zip (no blank ever overwrites)
  * court mailing is NOT the property itself (at-property = occupied class,
    separate decision — hold rules, not this sweep)
  * record located unambiguously (UUID from court_pr_renames_20260823 first,
    street search + surname fallback + house-number filter second)
  * live owner IS the court PR (first+last, case-insensitive). A DP-set or
    hand-set different name is never redirected to the court PR's address.
  * live mailing is still the property (or blank). A mailing someone already
    moved elsewhere is a human call, not a sweep target.
Every write is verified by GET refetch (search index is stale after writes).

    python court_mailing_sweep_20260826.py            # DRY RUN (GETs only)
    python court_mailing_sweep_20260826.py --apply    # live
"""
from __future__ import annotations

import copy
import csv
import datetime as _dt
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
OUT = REPO / "output" / f"court_mailing_sweep_20260826{'' if APPLY else '_dryrun'}.csv"
TAG = "Court Mailing Applied"
RENAME_MARKERS = {"PR Corrected", "PR From Court", "Phones - Other Heir"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# DataSift normalizes street suffixes on save ("Ebony Road" comes back
# "Ebony Rd"), so compare with both sides suffix-normalized or every
# verify false-fails (seen on the first live run: 9 of 15 "VOID SAVE"
# rows had actually saved fine).
_SUFFIX_MAP = {
    "road": "rd", "drive": "dr", "lane": "ln", "street": "st",
    "avenue": "ave", "court": "ct", "circle": "cir", "place": "pl",
    "boulevard": "blvd", "trail": "trl", "highway": "hwy", "parkway": "pkwy",
    "terrace": "ter", "north": "n", "south": "s", "east": "e", "west": "w",
    "northwest": "nw", "northeast": "ne", "southwest": "sw", "southeast": "se",
    "apartment": "apt", "unit": "unit", "suite": "ste",
}


def street_norm(s: str) -> str:
    toks = re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).split()
    return "".join(_SUFFIX_MAP.get(t, t) for t in toks)


def house_no(street: str) -> str:
    return ((street or "").strip().split() or [""])[0].lower()


def parse_mailing(raw: str) -> dict | None:
    """'7816 EBONY ROAD, CHARLOTTE, NC, 28216' -> street/city/state/zip.

    Tolerates 'STREET, CITY, NC 28216' (state+zip in one part)."""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if len(parts) == 3:
        m = re.match(r"^([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)$", parts[2])
        if m:
            parts = [parts[0], parts[1], m.group(1), m.group(2)]
    if len(parts) != 4:
        return None
    street, city, state, zipc = parts
    if not re.match(r"^\d{5}(-\d{4})?$", zipc) or len(state) != 2:
        return None
    if not street or not city:
        return None
    return {"street": street.title(), "city": city.title(),
            "state": state.upper(), "zip": zipc}


def get_prop(h: dict, uuid: str) -> dict | None:
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        return None
    d = r.json()
    return d.get("data") or d.get("result") or d


def search(h: dict, text: str) -> list:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      data=json.dumps({"query": {"must": {"search": text}},
                                       "limit": 200}), timeout=30)
    if r.status_code != 200:
        return []
    d = r.json()
    return d.get("results") or d.get("data") or []


def locate(h: dict, street: str, surname: str) -> tuple:
    num = house_no(street)
    note = ""
    for q in ([street] if street else []) + ([surname] if surname else []):
        hits = search(h, q)
        if len(hits) == 1:
            return hits[0], ""
        if len(hits) > 1:
            exact = hits
            if num:
                exact = [x for x in exact
                         if ((x.get("address") or {}).get("street") or "")
                         .lower().startswith(num + " ")]
            if len(exact) == 1:
                return exact[0], ""
            note = f"{len(hits)} hits on {q!r} ({len(exact)} after house-no filter)"
    return None, note or "no hits"


def uuid_hints() -> dict[str, str]:
    """Case No. -> UUID from the 8/23 rename run files (live first)."""
    hints: dict[str, str] = {}
    for name in ("court_pr_renames_20260823_dryrun.csv",
                 "court_pr_renames_20260823.csv"):
        p = REPO / "output" / name
        if not p.exists():
            continue
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if (r.get("UUID") or "").strip():
                hints[r["Case No."]] = r["UUID"].strip()
    return hints


def tag_titles(rec: dict) -> list[str]:
    return [t.get("title") if isinstance(t, dict) else str(t)
            for t in (rec.get("tags") or [])]


def main() -> int:
    print(f"===== court-mailing sweep {'LIVE' if APPLY else 'DRY RUN'} "
          f"at {_dt.datetime.now()} =====")
    probe = [r for r in csv.DictReader(
        open(REPO / "output" / "heirs_pr_probe.csv", encoding="utf-8-sig"))
        if (r.get("Verdict") or "").strip() == "PR FOUND"]
    print(f"probe rows with a court PR: {len(probe)}")
    hints = uuid_hints()

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    rows, n_ready, n_skip, n_fail = [], 0, 0, 0
    for i, q in enumerate(probe, 1):
        case = q["Case No."]
        court = (q["Court PR"] or "").strip()
        street = (q["Property"] or "").strip()
        dec = (q["Decedent"] or "").strip()
        surname = dec.split(",")[0].strip() if "," in dec else (dec.split() or [""])[-1]
        out = {"Case No.": case, "County": q["County"], "Decedent": dec,
               "Court PR": court, "UUID": "", "Live Owner": "",
               "Mailing Before": "", "Mailing After (court)": q["PR Mailing"],
               "Calls Made": "", "SMS Attempts": "", "Mail Attempts": "",
               "Status": "", "Phones": "", "Renamed": "", "Result": "", "Note": ""}
        print(f"\n[{i}/{len(probe)}] {case}  {q['County']}  {dec[:34]}")

        def emit(result: str, note: str = ""):
            out["Result"], out["Note"] = result, note
            rows.append(out)

        want = parse_mailing(q["PR Mailing"])
        if not want:
            print(f"  court mailing unparseable: {q['PR Mailing']!r} - SKIP")
            emit("SKIP unparseable mailing"); n_skip += 1
            continue
        if house_no(want["street"]) == house_no(street) and house_no(street):
            print("  court mailing IS the property - occupied class, hold rules - SKIP")
            emit("SKIP at property (occupied class)"); n_skip += 1
            continue
        if len(court.split()) < 2:
            emit("SKIP bad court PR name"); n_skip += 1
            continue
        c_first, c_last = court.split()[0].lower(), court.split()[-1].lower()

        rec = get_prop(h, hints[case]) if case in hints else None
        if rec is None:
            rec, note = locate(h, street, surname)
            if rec is None:
                print(f"  NOT FOUND ({note}) - SKIP")
                emit("NOT FOUND", note); n_skip += 1
                continue
        uuid = rec.get("uuid")
        full = get_prop(h, uuid)
        if not full:
            emit("GET FAILED"); n_fail += 1
            continue

        owner = full.get("owner") or {}
        oa = owner.get("address") or {}
        pa = full.get("address") or {}
        live = (f"{(owner.get('first_name') or '').strip()} "
                f"{(owner.get('last_name') or '').strip()}").strip()
        calls = full.get("predictivecall_attempts") or 0
        out.update({
            "UUID": uuid, "Live Owner": live,
            "Mailing Before": ", ".join(x for x in [oa.get("street"), oa.get("city"),
                                                    oa.get("postal_code")] if x),
            "Calls Made": calls,
            "SMS Attempts": full.get("sms_attempts") or 0,
            "Mail Attempts": full.get("directmail_attempts") or 0,
            "Status": full.get("status") or "",
            "Phones": len(owner.get("phones") or []),
        })
        print(f"  live owner {live!r}  mailing {out['Mailing Before']!r}  "
              f"calls={calls} status={out['Status'] or '(default)'}")

        # guard: the located record must be the right house
        if house_no(street) and not ((pa.get("street") or "").lower()
                                     .startswith(house_no(street))):
            print("  located record street mismatch - SKIP")
            emit("SKIP wrong record located",
                 f"live street {pa.get('street')!r}"); n_skip += 1
            continue
        # guard: live owner must BE the court PR
        l_first = (owner.get("first_name") or "").strip().lower()
        l_last = (owner.get("last_name") or "").strip().lower()
        if l_last != c_last or l_first != c_first:
            print(f"  owner {live!r} is not court PR {court!r} - SKIP, human call")
            emit("SKIP owner is not the court PR"); n_skip += 1
            continue
        # guard: live mailing must still be the property (or blank / already court)
        lm, lp = street_norm(oa.get("street") or ""), street_norm(pa.get("street") or "")
        already = street_norm(want["street"]) == lm
        if lm and lm != lp and not already:
            print(f"  mailing already moved elsewhere ({out['Mailing Before']}) "
                  "- SKIP, human call")
            emit("SKIP mailing moved by someone"); n_skip += 1
            continue

        renamed = bool(set(tag_titles(full)) & RENAME_MARKERS)
        out["Renamed"] = "yes" if renamed else "no"
        needs_addr = not already
        # calls + status reset ONLY for renamed records — an already-named
        # record's dials/dispositions were with the right person and stand.
        needs_calls = renamed and calls != 0
        needs_status = renamed and bool(full.get("status"))
        needs_tag = TAG not in tag_titles(full)
        planned = [x for x, need in
                   [("mailing->court", needs_addr), ("calls->0", needs_calls),
                    ("status->default", needs_status), (f"tag '{TAG}'", needs_tag)]
                   if need]
        if not planned:
            print("  nothing to do (already swept)")
            emit("OK already swept"); n_ready += 1
            continue
        print("  planned: " + ", ".join(planned))

        if not APPLY:
            emit("DRY " + " | ".join(planned)); n_ready += 1
            continue

        # --- write 1: owner.address (full owner round-trip, address mutated) ---
        good = True
        if needs_addr:
            new_owner = copy.deepcopy(owner)
            na = new_owner.get("address") or {}
            na.update({"street": want["street"], "city": want["city"],
                       "state": want["state"], "postal_code": want["zip"]})
            new_owner["address"] = na
            r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                               data=json.dumps({"owner": new_owner}), timeout=30)
            good = r.status_code in (200, 202)
            print(f"  PATCH owner.address -> {r.status_code}")
        # --- write 2: ticker + status ---
        if good and (needs_calls or needs_status):
            body = {}
            if needs_calls:
                body["predictivecall_attempts"] = 0
            if needs_status:
                body["status"] = None
            r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                               data=json.dumps(body), timeout=30)
            good = good and r.status_code in (200, 202)
            print(f"  PATCH {list(body)} -> {r.status_code}")
        # --- write 3: tag ---
        if good and needs_tag:
            r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                              headers=h, data=json.dumps({"tags": [TAG]}), timeout=30)
            good = good and r.status_code in (200, 201, 202)
            print(f"  add-tags -> {r.status_code}")

        # --- verify by refetch (never trust the write, never trust search) ---
        time.sleep(0.4)
        v = get_prop(h, uuid) or {}
        va = (v.get("owner") or {}).get("address") or {}
        v_calls = v.get("predictivecall_attempts") or 0
        v_status = v.get("status")
        v_tag = TAG in tag_titles(v)
        stuck = ((not needs_addr
                  or street_norm(va.get("street") or "") == street_norm(want["street"]))
                 and (not needs_calls or v_calls == 0)
                 and (not needs_status or not v_status)
                 and (not needs_tag or v_tag))
        out["Mailing Before"] = out["Mailing Before"]  # keep pre-state in the CSV
        print(f"  VERIFY: mailing={va.get('street')!r} calls={v_calls} "
              f"status={v_status!r} tag={'yes' if v_tag else 'NO'} -> "
              f"{'OK' if stuck else 'DID NOT STICK'}")
        if stuck:
            emit("APPLIED " + " | ".join(planned)); n_ready += 1
        else:
            emit("VOID SAVE — verify by hand",
                 f"mailing={va.get('street')!r} calls={v_calls} "
                 f"status={v_status!r} tag={v_tag}"); n_fail += 1

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n===== {'applied' if APPLY else 'would apply'}: {n_ready}   "
          f"skipped: {n_skip}   failed: {n_fail}")
    print(f"results -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
