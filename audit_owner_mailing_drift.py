"""Nightly: catch records whose OWNER changed while the mailing stayed behind.

Renaming a DataSift record does not move its mailing address. So when a record
is PR-corrected by hand — Oren does this and tags them "PR Corrected" /
"Phones - Other Heir" — the previous heir's address is left sitting under the
new heir's name, and the next mail drop goes to the wrong person's house.

Found 2026-08-23: 2 of the 15 records repointed the day before had drifted this
way overnight (26E000978-170 Richard Sigmon -> Rebecca Albrecht kept Sigmon's
9466 Westridge Dr; 26E002979-590 Arceal Dudley -> Korey Dudley kept Dudley's
1941 Booker Dr). Both were caught by hand. This makes it automatic.

Method: snapshot (owner name, mailing street) per record, diff on the next run.
  * owner changed AND mailing unchanged      -> DRIFT (the bug)
  * owner changed AND mailing changed too    -> fine, whoever renamed it also
                                                moved the address
  * owner unchanged                          -> fine
First run only builds the snapshot, so it reports nothing — that is expected.

Writes NOTHING to DataSift. Every call is a GET. Non-fatal by design: any error
is logged and the exit code stays 0 so the nightly never dies on a report step.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\audit_owner_mailing_drift.py

Env:  NC_MAILING_DRIFT=0        skip entirely (also the nightly's off-switch)
      NC_DRIFT_MAX_RECORDS=N    cap the GETs (default 400)
Files: output/.owner_mailing_snapshot.json   state
       output/owner_mailing_drift.csv        flagged rows (rewritten each run)
"""
from __future__ import annotations

import csv
import datetime as _dt
import glob
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402

API = "https://apiv2.reisift.io"
SNAP = REPO / "output" / ".owner_mailing_snapshot.json"
OUT = REPO / "output" / "owner_mailing_drift.csv"
MAX_RECORDS = int(os.environ.get("NC_DRIFT_MAX_RECORDS", "400") or 400)

# Every audit/push CSV that carries a UUID column is a source of records worth
# watching — the DP'd population plus anything we have ever written a mailing to.
SOURCES = ("dm_mailing_gap_*.csv", "dm_mailing_push_*.csv", "court_mailing_push_*.csv",
           "wrong_person_audit_*.csv", "dp_rename_push_*.csv", "rename_gap_audit_*.csv")


def log(msg: str) -> None:
    print(f"{_dt.datetime.now():%H:%M:%S} {msg}", flush=True)


def watched() -> dict[str, str]:
    """uuid -> case no (or a street, when the row has no case)."""
    out: dict[str, str] = {}
    for pat in SOURCES:
        for f in glob.glob(str(REPO / "output" / pat)):
            try:
                fh = open(f, encoding="utf-8-sig", newline="")
            except OSError:
                continue
            with fh:
                for r in csv.DictReader(fh):
                    u = (r.get("UUID") or "").strip()
                    if not u:
                        continue
                    label = (r.get("Case No.") or r.get("Property") or "").strip()
                    if u not in out or (label and not out[u]):
                        out[u] = label
    return out


def token_or_none() -> str | None:
    try:
        from audit_rename_gap_20260822 import token
    except Exception as e:  # noqa: BLE001
        log(f"cannot import token helper ({e}) — skipping")
        return None
    for attempt in range(3):
        try:
            t = token()
        except Exception as e:  # noqa: BLE001
            log(f"  login attempt {attempt + 1} raised {type(e).__name__} — retrying")
            t = None
        if t:
            return t
        time.sleep(3)
    return None


def main() -> int:
    if os.environ.get("NC_MAILING_DRIFT") == "0":
        log("skipped — NC_MAILING_DRIFT=0")
        return 0
    log("owner/mailing drift check")

    recs = watched()
    log(f"watching {len(recs)} record(s) from {len(SOURCES)} audit/push file patterns")
    if not recs:
        return 0
    try:
        snap = json.loads(SNAP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        snap = {}
    first_run = not snap
    if first_run:
        log("no snapshot yet — this run only records the baseline")

    tok = token_or_none()
    if not tok:
        log("login failed — nothing checked (non-fatal)")
        return 0
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": "Bearer " + tok,
         "content-type": "application/json"}

    drift, checked, gone = [], 0, 0
    for uuid, label in list(recs.items())[:MAX_RECORDS]:
        try:
            r = requests.get(API + "/api/internal/property/" + uuid + "/",
                             headers=h, timeout=30)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            gone += 1
            continue
        d = r.json()
        d = d.get("data") or d.get("result") or d
        o = d.get("owner") or {}
        owner = ((o.get("first_name") or "").strip() + " "
                 + (o.get("last_name") or "").strip()).strip()
        mail = ((o.get("address") or {}).get("street") or "").strip()
        checked += 1

        was = snap.get(uuid)
        drifted = bool(was) and (was.get("owner") or "") != owner \
            and (was.get("mail") or "") == mail
        if drifted:
            tags = [t.get("title") if isinstance(t, dict) else str(t)
                    for t in (d.get("tags") or [])]
            drift.append({
                "Case No.": label, "Was Owner": was.get("owner") or "",
                "Now Owner": owner, "Mailing (unchanged)": mail,
                "Property": ((d.get("address") or {}).get("street") or ""),
                "Tags": "; ".join(t for t in tags if "Correct" in t or "Heir" in t),
                "UUID": uuid})
            # Keep the OLD owner in the snapshot so this keeps firing every night
            # until someone fixes the mailing. Updating it here would make the
            # alert appear exactly once, in one night's log, and then go quiet —
            # which is how a real one gets missed.
            snap[uuid] = {**was, "seen": _dt.date.today().isoformat()}
        else:
            snap[uuid] = {"owner": owner, "mail": mail,
                          "seen": _dt.date.today().isoformat()}

    SNAP.parent.mkdir(parents=True, exist_ok=True)
    SNAP.write_text(json.dumps(snap, indent=1), encoding="utf-8")

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Case No.", "Was Owner", "Now Owner",
                                           "Mailing (unchanged)", "Property",
                                           "Tags", "UUID"])
        w.writeheader()
        w.writerows(drift)

    log(f"checked {checked}; {gone} unreachable; snapshot now {len(snap)} record(s)")
    if drift:
        log(f"*** {len(drift)} RECORD(S) RENAMED BUT STILL MAILING THE OLD HEIR ***")
        for x in drift:
            log(f"    {x['Case No.'] or x['Property']}: {x['Was Owner']!r} -> "
                f"{x['Now Owner']!r}, mailing still {x['Mailing (unchanged)']!r}")
        log(f"    detail: {OUT}")
    elif not first_run:
        log("no drift")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"non-fatal error: {type(e).__name__}: {e}")
        raise SystemExit(0)
