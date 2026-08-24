"""Fill in the real PR on the "Heirs of ..." records the court names (Oren approved 8/23).

Source: output/heirs_pr_probe.csv, rows with Verdict == "PR FOUND" (off-site only -
the 5 "PR FOUND - but occupied" rows are a SEPARATE decision and are excluded here).

These records are not wrong, they are blank: the owner still reads "Heirs <surname>"
because the inverted guard in backfill_case_numbers_from_ecourts.py blocked the
upgrade for months (see [[project_court_pr_beats_dp_guess]]).

Per record:
  - owner first/last -> the court's PR
  - personal_representative -> the court's PR, but ONLY if it is blank or still
    the "Heirs of ..." placeholder; a real PR someone else set is left alone
  - tag "PR From Court"
  - tag "Phones - Other Heir" when the record already carries phones: those were
    skip-traced against the decedent/heirs, NOT against the court's PR, so the
    caller must not assume the numbers reach the named person (Oren 8/23).

NOT touched: phones, emails, mailing, lists, status, custom fields, other tags.
Mailing deliberately left alone - changing where the mail goes is a separate call.

Guards - all must pass or the record is skipped:
  1. the record is located unambiguously (street search, surname fallback,
     house-number disambiguation - same workhorse as audit_rename_gap_20260822)
  2. live owner first name starts with heirs/heir/estate (still a placeholder).
     A record already carrying a real name is NEVER overwritten.
  3. house number of the located record matches the probe's property address
  4. court PR is present and splits into at least two tokens
Verifies every write with a GET refetch - the SEARCH index is stale after writes.

    python push_court_pr_renames_20260823.py            # DRY RUN
    python push_court_pr_renames_20260823.py --apply    # live
"""
from __future__ import annotations

import copy
import csv
import datetime as _dt
import json
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
OUT = REPO / "output" / f"court_pr_renames_20260823{'' if APPLY else '_dryrun'}.csv"
PLACEHOLDER = ("heirs", "heir", "estate")

_NAME_NOISE = {"JR", "SR", "II", "III", "IV"}


def name_tokens(name: str) -> set:
    """Comparable name parts, order-free — 'Poplin, Rebecca White' and
    'Rebecca Poplin' share {POPLIN, REBECCA}."""
    return {t.upper().strip(".") for t in (name or "").replace(",", " ").split()
            if len(t.strip(".")) > 2 and t.upper().strip(".") not in _NAME_NOISE}


def owner_is_decedent(live: str, decedent: str, court_pr: str) -> bool:
    """True when the CRM owner is the DEAD person, not a representative.

    The 'already named' guard below exists so a human's correction is never
    stomped — but it only recognised the 'Heirs of ...' placeholder, so a record
    still carrying the decedent's own name read as a real PR and was skipped.
    26E000666-480 (owner 'Ted Stokes', court PR Sheril Summers) and
    26E000508-480 (owner 'Rebecca Poplin', court PR Michelle Baggarley) both
    sat that way: marketing addressed to someone who has died.

    Subset, not equality — the CRM holds 'Rebecca Poplin' where the court writes
    'Poplin, Rebecca White'. Guarded against the common case where the PR is a
    relative sharing the surname: if the live name is equally consistent with
    the court's PR, this stays False and the record is left alone.
    """
    live_t, dec_t, pr_t = (name_tokens(live), name_tokens(decedent),
                           name_tokens(court_pr))
    if not live_t or not dec_t:
        return False
    return live_t <= dec_t and live_t != pr_t and not live_t <= pr_t


def titles(tags) -> list:
    return [t.get("title") if isinstance(t, dict) else str(t) for t in (tags or [])]


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
    """(record, note) - street search first, surname fallback, house-no filter."""
    num = (street.split() or [""])[0].lower() if street else ""
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


def main() -> int:
    print(f"===== court-PR renames {'LIVE' if APPLY else 'DRY RUN'} "
          f"at {_dt.datetime.now()} =====")
    rows_in = [r for r in csv.DictReader(
        open(REPO / "output" / "heirs_pr_probe.csv", encoding="utf-8-sig"))
        if r["Verdict"] == "PR FOUND"]
    print(f"targets (off-site formal PR): {len(rows_in)}")

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    out, ok, skipped, failed, mail_diff = [], 0, 0, 0, 0
    for i, q in enumerate(rows_in, 1):
        case, court = q["Case No."], (q["Court PR"] or "").strip()
        street, dec = (q["Property"] or "").strip(), (q["Decedent"] or "").strip()
        surname = dec.split(",")[0].strip() if "," in dec else (dec.split() or [""])[-1]
        rec_out = {"Case No.": case, "County": q["County"], "Decedent": dec,
                   "Court PR": court, "Court Role": q["Court Role"],
                   "Was": "", "Now": "", "UUID": "", "Result": "", "Note": ""}
        print(f"\n[{i}/{len(rows_in)}] {case}  {q['County']}  {dec[:34]}")

        if len(court.split()) < 2:
            print(f"  court PR {court!r} unusable - SKIP")
            rec_out["Result"] = "SKIP bad PR"; out.append(rec_out); skipped += 1
            continue
        first, last = court.split()[0], court.split()[-1]

        rec, note = locate(h, street, surname)
        if rec is None:
            print(f"  NOT FOUND in DataSift ({note}) - SKIP")
            rec_out["Result"] = "NOT FOUND"; rec_out["Note"] = note
            out.append(rec_out); skipped += 1
            continue

        uuid = rec.get("uuid")
        o = rec.get("owner") or {}
        live = (f"{(o.get('first_name') or '').strip()} "
                f"{(o.get('last_name') or '').strip()}").strip()
        live_street = ((rec.get("address") or {}).get("street") or "").strip()
        rec_out["UUID"], rec_out["Was"] = uuid, live

        num = (street.split() or [""])[0].lower()
        if num and not live_street.lower().startswith(num):
            print(f"  GUARD: {live_street!r} does not start {num!r} - SKIP")
            rec_out["Result"] = "SKIP address"; out.append(rec_out); skipped += 1
            continue
        is_placeholder = (o.get("first_name") or "").strip().lower().startswith(PLACEHOLDER)
        is_decedent = owner_is_decedent(live, q.get("Decedent", ""), court)
        if not is_placeholder and not is_decedent:
            print(f"  owner is already a real name ({live!r}) - SKIP, not overwriting")
            rec_out["Result"] = "SKIP already named"; out.append(rec_out); skipped += 1
            continue
        if is_decedent:
            print(f"  owner {live!r} IS THE DECEDENT - correcting to the court's PR")
            rec_out["Note"] = "owner was the decedent"

        # full record for phones / PR (search results are trimmed)
        rf = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        d = rf.json() if rf.status_code == 200 else {}
        d = d.get("data") or d.get("result") or d
        owner = d.get("owner") or o
        live_pr = (d.get("personal_representative") or "").strip()
        nph = len(owner.get("phones") or [])

        new_owner = copy.deepcopy(owner)
        new_owner["first_name"], new_owner["last_name"] = first, last
        body = {"owner": new_owner}
        if (not live_pr) or live_pr.lower().startswith("heirs of"):
            body["personal_representative"] = court
        else:
            print(f"  PR already {live_pr!r} - left as-is")

        tags = ["PR From Court"] + (["Phones - Other Heir"] if nph else [])
        if q["PR Mailing"]:
            mail_diff += 1
        print(f"  {live!r} -> {first} {last!r} ({q['Court Role']}); phones {nph}; "
              f"tags +{tags}")

        if not APPLY:
            rec_out["Now"] = f"{first} {last}"; rec_out["Result"] = "DRY"
            out.append(rec_out); ok += 1
            continue

        r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json=body, timeout=30)
        if r.status_code not in (200, 202):
            print(f"  PATCH -> {r.status_code} {r.text[:110]}")
            rec_out["Result"] = f"PATCH {r.status_code}"
            out.append(rec_out); failed += 1
            continue
        rt = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                           headers=h, json={"tags": tags}, timeout=30)

        v = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        vd = v.json() if v.status_code == 200 else {}
        vd = vd.get("data") or vd.get("result") or vd
        vo = vd.get("owner") or {}
        after = (f"{(vo.get('first_name') or '').strip()} "
                 f"{(vo.get('last_name') or '').strip()}").strip()
        good = after.lower() == f"{first} {last}".lower()
        tags_ok = all(t in titles(vd.get("tags")) for t in tags)
        print(f"  PATCH {r.status_code} / tags {rt.status_code} / VERIFY {after!r} "
              f"phones={len(vo.get('phones') or [])} tags_ok={tags_ok} "
              f"-> {'OK' if good else 'DID NOT STICK'}")
        rec_out["Now"] = after
        rec_out["Result"] = "RENAMED" if good and tags_ok else "PARTIAL" if good else "VOID"
        out.append(rec_out)
        ok += good
        failed += (not good)
        time.sleep(0.4)

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    print(f"\n==== {'LIVE' if APPLY else 'DRY'} SUMMARY ====")
    print(f"  renamed {ok}   skipped {skipped}   failed {failed}")
    print(f"  {mail_diff} of the renamed have a court mailing address on file "
          f"(mailing NOT changed - separate decision)")
    print(f"wrote {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
