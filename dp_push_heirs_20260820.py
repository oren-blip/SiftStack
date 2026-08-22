"""DP push, heirs-of backlog sweep 2026-08-20 — Oren runs this himself (the
auto-mode classifier blocks Claude's DataSift writes):

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push_heirs_20260820.py --dry-run  # preview
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push_heirs_20260820.py            # real

For every RESOLVED case in output/dp_heirs_sweep_20260820/results.json:
  - finds the DataSift record by property street, guarded to owner
    first_name == "Heirs" + last_name == decedent's last (never renames a
    record that already has a real person on it)
  - renames the owner to the verified DM (heir)
  - if the DM lives elsewhere, points the mailing at the DM's address
    (never blanks over existing values — pr_upgrade lesson)
  - appends new Trestle-tiered phones (score >= 21; litigator numbers get
    "Litigator - DNC" and no dial tier)
  - tags "DP Complete"; DM-at-property also gets "Hold Review - Occupied"
    (review flag only — no de-listing without Oren's call)
  - re-GETs and verifies phones + tags landed

Rerun-safe: records already carrying "DP Complete" are skipped.
Findings: output/reports/DP_HeirsSweep_20260820.md
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from dp_push_20260819 import API, token  # noqa: E402

DRY = "--dry-run" in sys.argv
RESULTS = REPO / "output" / "dp_heirs_sweep_20260820" / "results.json"
LOG = REPO / "logs" / "dp_push_heirs_20260820.log"


def tier(score) -> str | None:
    if score is None:
        return None
    s = int(score)
    if s >= 81:
        return "Dial First"
    if s >= 61:
        return "Dial Second"
    if s >= 41:
        return "Dial Third"
    if s >= 21:
        return "Dial Fourth"
    return None


def headers(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}", "content-type": "application/json",
            "accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7"}


def find_record(h: dict, street: str, dec_last: str) -> dict | None:
    """Search by street, accept only the Heirs-of record for this decedent."""
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": street}}}, timeout=30)
    if r.status_code != 200:
        print(f"  search {street!r} -> HTTP {r.status_code}")
        return None
    hits = []
    for rec in r.json().get("results", []):
        ow = rec.get("owner") or {}
        if (ow.get("first_name") or "").strip().lower() != "heirs":
            continue
        if (ow.get("last_name") or "").strip().lower() != dec_last.strip().lower():
            continue
        if ((rec.get("address") or {}).get("street") or "").strip().lower() \
                != street.strip().lower():
            continue
        hits.append(rec)
    if len(hits) != 1:
        print(f"  search {street!r} owner 'Heirs {dec_last}': {len(hits)} match(es) — SKIP")
        return None
    return hits[0]


def parse_full_address(full: str) -> dict | None:
    """'123 Main St; Charlotte, NC 28205-1234' -> mailing dict, or None.
    Enformion separates street from city with a semicolon."""
    parts = [p.strip() for p in (full or "").replace(";", ",").split(",")
             if p.strip()]
    if len(parts) < 3:
        return None
    m = re.search(r"([A-Z]{2})\s+(\d{5})(?:-\d{4})?", parts[-1])
    if not m:
        return None
    return {"street": ", ".join(parts[:-2]) if len(parts) > 3 else parts[0],
            "city": parts[-2], "state": m.group(1), "postal_code": m.group(2)}


def main() -> int:
    entries = [e for e in json.loads(RESULTS.read_text(encoding="utf-8"))
               if e.get("outcome") == "resolved"]
    log = LOG.open("a", encoding="utf-8")

    def out(text: str) -> None:
        print(text)
        log.write(text + "\n")
        log.flush()

    out(f"\n===== run at {_dt.datetime.now()} dry_run={DRY} — "
        f"{len(entries)} resolved case(s)")
    h = headers(token())
    ok = skipped = 0
    for e in entries:
        dm = e["dm"]
        dec_last = e["decedent"].split(",")[0].strip() if "," in e["decedent"] \
            else e["decedent"].split()[-1]
        label = f"{e['case_no']} {dec_last} @ {e['property']}"
        out(f"\n=== {label}")

        rec = find_record(h, e["property"], dec_last)
        if not rec:
            skipped += 1
            continue
        uuid = rec.get("uuid")
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code != 200:
            out(f"  GET {uuid} -> {r.status_code} — SKIP")
            skipped += 1
            continue
        d = r.json()
        tags_now = [t.get("title") if isinstance(t, dict) else str(t)
                    for t in (d.get("tags") or [])]
        if "DP Complete" in tags_now:
            out("  already DP Complete — skip (rerun-safe)")
            ok += 1
            continue
        owner = d.get("owner") or {}
        existing = {"".join(c for c in str(p.get("number") or "") if c.isdigit())[-10:]
                    for p in (owner.get("phones") or [])}

        new_owner = copy.deepcopy(owner)
        new_owner["first_name"] = dm["first"]
        new_owner["last_name"] = dm["last"]

        mail_note = "mailing unchanged (DM at property)" if dm["occupied_flag"] \
            else "mailing unchanged (no parseable DM address)"
        if not dm["occupied_flag"]:
            parsed = parse_full_address(dm.get("address") or "")
            if parsed and all(parsed.values()):
                # The mailing address lives on owner["address"] — the top-level
                # property "address" is the situs. This block used to write
                # owner["mailing_address"], a key the API does not read: the
                # PATCH still returned HTTP 200 and the rename/phones in the
                # same body landed, so every run looked clean while 0 of 16
                # mailings actually saved (found 2026-08-22, see
                # audit_dm_mailing_gap_20260822.py). Same key the proven
                # dp_fix_mailings_20260817.py recipe uses.
                ma = new_owner.get("address") or {}
                ma.update({"street": parsed["street"], "city": parsed["city"],
                           "state": parsed["state"],
                           "postal_code": parsed["postal_code"]})
                new_owner["address"] = ma
                mail_note = f"mailing -> {parsed['street']}, {parsed['city']} " \
                            f"{parsed['state']} {parsed['postal_code']}"

        added = []
        for s in (e.get("scored") or []):
            t = "Litigator - DNC" if s.get("litigator") else tier(s.get("score"))
            if not t:
                continue
            num = s["phone"]
            if num[-10:] in existing:
                out(f"  phone {num} already on record — skip")
                continue
            ltype = "MOBILE" if "mobile" in str(s.get("line_type") or "").lower() \
                else "LANDLINE"
            rel_tag = f"{dm['relationship']} {dm['first']} {dm['last']}"
            new_owner.setdefault("phones", []).append(
                {"number": num, "type": ltype, "tags": [t, rel_tag]})
            added.append(num)

        add_tags = ["DP Complete"]
        if dm["occupied_flag"]:
            add_tags.append("Hold Review - Occupied")
        out(f"  rename 'Heirs {dec_last}' -> {dm['first']} {dm['last']} "
            f"({dm['relationship']}); {mail_note}; +{len(added)} phone(s); "
            f"tags {add_tags}")
        if DRY:
            ok += 1
            continue

        r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"owner": new_owner}, timeout=30)
        out(f"  PATCH owner -> HTTP {r.status_code}")
        if r.status_code != 200:
            out(f"    {r.text[:200]} — SKIPPING tags")
            skipped += 1
            continue
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h, json={"tags": add_tags}, timeout=30)
        out(f"  add-tags {add_tags} -> HTTP {r.status_code}")

        # verify
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code == 200:
            d2 = r.json()
            ow2 = d2.get("owner") or {}
            nums = {"".join(c for c in str(p.get("number") or "") if c.isdigit())[-10:]
                    for p in (ow2.get("phones") or [])}
            missing = [n for n in added if n[-10:] not in nums]
            tags2 = [t.get("title") if isinstance(t, dict) else str(t)
                     for t in (d2.get("tags") or [])]
            renamed = (ow2.get("last_name") or "").lower() == dm["last"].lower()
            # verify the mailing too — the silent no-op above hid for two days
            # because this line only ever checked the name, phones and tag
            want_mail = mail_note.startswith("mailing -> ")
            mail_ok = True
            if want_mail:
                live_mail = ((ow2.get("address") or {}).get("street") or "").strip()
                mail_ok = live_mail.lower() == parsed["street"].lower()
            out(f"  verify: renamed={renamed} phones_missing={missing} "
                f"dp_complete={'DP Complete' in tags2}"
                + (f" mailing_saved={mail_ok}" if want_mail else ""))
            if renamed and not missing and mail_ok:
                ok += 1

    out(f"\n{ok} pushed/verified, {skipped} skipped, of {len(entries)} resolved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
