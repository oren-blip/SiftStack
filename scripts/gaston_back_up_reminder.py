"""Ping Gaston County GIS until it answers, then Slack Oren the two Week 31
Gaston cases waiting on it — and delete this one-shot scheduled task.

Gaston GIS has a nightly maintenance window (~9pm-7:30am), so a fixed-time
reminder can still land on a dead endpoint. This polls instead: it fires the
message on the FIRST successful parcel query, or gives up after MAX_MINUTES
and says so rather than staying silent.

Registered as Task Scheduler job "SiftStack Gaston GIS Reminder".
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(r"D:\SiftStack")
TASK_NAME = "SiftStack Gaston GIS Reminder"
GASTON_URL = ("https://gis.gastoncountync.gov/publicgis/rest/services/"
              "PublicGIS/Parcels/MapServer/11/query")
POLL_SECONDS = 300
MAX_MINUTES = 180

MESSAGE = """:round_pushpin: *Gaston GIS is back up* - the two Week 31 PR conflicts are ready to review.

*1. Waldroup 26E000997-350* (Disposed-Clerk, 200 Colt Thornburg Rd, Dallas - mobile home, $38K)
DataSift contact *Joy McClure* (2176 Devine Rd, Iron Station) appears NOWHERE in the court record - same stale bulk-list pattern as Kachmarik/Barnett.
*Look for:* the applicant's name is nearly identical to the decedent's - court shows decedent "Wald*ru*p, Michael Shane" and applicant "Wald*rou*p, Michael Shane" @ 1206 Haywood Ct, Lincolnton. Confirm it's the SON, not the decedent typo'd onto his own estate (different address + spelling say son).
If son: `python pr_upgrade_step.py --week 31 --fix-case 26E000997-350`
Bonus: cheap MH on land in a Disposed estate = your un-detitled mobile-home niche.

*2. Russell 26E001013-350* (Pending, 1700 Gaither Rd, Belmont, SFR $426K) - *do NOT blanket-fix*
*Wanda McCormick is REAL* - the court lists "McCormick, Wanda Russell" as a Beneficiary at 325 Gaither Rd, same road as the property (almost certainly the decedent's daughter). Overwriting her would throw away a genuine family contact.
*Look for:*
- Two signers: Co-Executors *Darrell Dean Russell* (202 S. Central Ave, Belmont) and *Gilbert Winfred Russell Jr* (2713 Rawhide Dr, Belmont). Both must sign.
- Our workbook mails Gilbert at *1700 Gaither Rd - the decedent's house*. Court says 2713 Rawhide Dr. Wrong either way.
- Name split is broken: First "Gilbert", Last "Winfred Russell, Jr" - needs a manual_corrections.csv line.
Suggestion: keep Wanda as contact, add Gilbert + Darrell as DM 2 / DM 3 with their real addresses, instead of --fix-case."""


def slack(text: str) -> None:
    url = ""
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("SLACK_WEBHOOK_URL="):
            url = line.split("=", 1)[1].strip()
            break
    if not url:
        print("no SLACK_WEBHOOK_URL")
        return
    r = requests.post(url, json={"text": text}, timeout=30)
    print("slack:", r.status_code)


def gaston_up() -> bool:
    try:
        # PID is a STRING field — an unquoted numeric comparison returns
        # HTTP 200 with {"error": {"code": 400, "message": "Unable to complete
        # operation."}}, which is indistinguishable from an outage. Quote it.
        # (This bug made the 2026-08-03 run report Gaston down while it was up.)
        r = requests.get(GASTON_URL, params={"where": "PID = '165896'",
                                             "outFields": "PID", "f": "json",
                                             "returnGeometry": "false"}, timeout=25)
        if r.status_code != 200:
            return False
        data = r.json()
        return bool(data.get("features")) and not data.get("error")
    except Exception:
        return False


def main() -> int:
    deadline = time.time() + MAX_MINUTES * 60
    up = False
    while time.time() < deadline:
        if gaston_up():
            up = True
            break
        time.sleep(POLL_SECONDS)
    if up:
        slack(MESSAGE)
    else:
        slack(":warning: Gaston GIS still not responding after "
              f"{MAX_MINUTES} min. The two Week 31 PR conflicts "
              "(26E000997-350 Waldroup, 26E001013-350 Russell) are still "
              "waiting - the court-record details are in the SiftStack session notes.")
    subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                   capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
