"""Daily NC pipeline report.

Runs as the final step of the 6 PM daily build. Reads the day's outputs,
builds a plain-text report, writes it to output/daily_report_YYYY-MM-DD.txt,
and optionally emails it via Gmail/Workspace SMTP.

Configured via .env (already loaded by the pipeline):
  SMTP_USER       — sender Gmail/Workspace address (e.g. oren@remedihomesolutions.com)
  SMTP_PASS       — Google app password (NOT your regular password)
  REPORT_TO       — comma-separated recipient list
  SMTP_HOST       — defaults to smtp.gmail.com
  SMTP_PORT       — defaults to 587 (TLS)

To run by hand:
    .venv\\Scripts\\python.exe scripts\\daily_report.py
    .venv\\Scripts\\python.exe scripts\\daily_report.py --no-email
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import smtplib
import sys
from collections import Counter
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

from openpyxl import load_workbook

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


OUTPUT = Path("output")
LOGS = Path("logs")


# ── Discovery ────────────────────────────────────────────────────────


def find_latest_workbook() -> Path | None:
    candidates = sorted(OUTPUT.glob("FTM_*_NC_Estates_throughWeek*.xlsx"))
    return candidates[-1] if candidates else None


def find_latest_datasift(week_n: int) -> Path | None:
    files = sorted(OUTPUT.glob(f"nc_estates_ftm_*_week{week_n}_datasift.csv"))
    return files[-1] if files else None


def find_yesterdays_datasift(week_n: int, today_path: Path) -> Path | None:
    """Datasift from a prior run — used to compute 'new today'."""
    files = sorted(OUTPUT.glob(f"nc_estates_ftm_*_week{week_n}_datasift.csv"))
    older = [f for f in files if f != today_path]
    return older[-1] if older else None


def find_latest_heir_transfer(week_n: int) -> Path | None:
    files = sorted(OUTPUT.glob(f"heir_transfer_review_week{week_n}_*.xlsx"))
    return files[-1] if files else None


# ── Parse outputs ────────────────────────────────────────────────────


def read_workbook_cases(wb_path: Path) -> tuple[int, list[dict]]:
    wb = load_workbook(wb_path, read_only=True)
    rows: list[dict] = []
    week_n = 0
    for sn in wb.sheetnames:
        m = re.search(r"Week (\d+)", sn)
        if m:
            week_n = max(week_n, int(m.group(1)))
        ws = wb[sn]
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            continue
        header = [str(c or "").strip() for c in all_rows[0]]
        for r in all_rows[1:]:
            d = {header[i]: r[i] for i in range(min(len(header), len(r)))}
            if (d.get("Case No.") or "").strip():
                d["_tab"] = sn
                rows.append(d)
    return week_n, rows


def read_csv_cases(path: Path) -> list[dict]:
    if not path or not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if (r.get("Case No.") or "").strip()]


def read_heir_transfer(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    wb = load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(c or "").strip() for c in rows[0]]
    out = []
    for r in rows[1:]:
        d = {header[i]: r[i] for i in range(min(len(header), len(r)))}
        if d.get("Case No."):
            out.append(d)
    return out


_DROP_PATTERNS = {
    "no_parcel":     re.compile(r"Dropped \(no parcel\): (\d+)"),
    "over_500k":     re.compile(r"Dropped >\$500K: (\d+)"),
    "heir_occupied": re.compile(r"Dropped heir-occupied: (\d+)"),
    "commercial":    re.compile(r"Dropped commercial: (\d+)"),
    "archive_dupe":  re.compile(r"Dropped archive-duplicate rows: (\d+)"),
    "non_pending":   re.compile(r"Dropped non-Pending: (\d+)"),
    "repick":        re.compile(r"REPICK "),
    "refound":       re.compile(r"Re-found correct parcels: (\d+)"),
}


def parse_polish_log(log_path: Path, since: datetime | None = None) -> dict:
    """Parse polish log for drop counts + matcher events. Robust to UTF-8/UTF-16."""
    out = {k: 0 for k in _DROP_PATTERNS}
    if not log_path.exists():
        return out
    # Try UTF-8 first, fall back to UTF-16
    text = ""
    for enc in ("utf-8", "utf-16-le", "utf-16"):
        try:
            text = log_path.read_text(encoding=enc, errors="ignore")
            if text:
                break
        except (OSError, UnicodeDecodeError):
            continue
    if since is not None:
        # Keep only lines from today's run boundary onward
        cutoff = since.strftime("%H:%M")
        marker = f"=== Daily run started"
        if marker in text:
            text = text[text.rindex(marker):]
    for key, pat in _DROP_PATTERNS.items():
        matches = pat.findall(text)
        if key == "repick":
            out[key] = len(matches)
            continue
        # Sum all matches — polish processes multiple weeks in one run, each
        # producing its own "Dropped X: N" line. Total across all weeks.
        total = 0
        for m in matches:
            try:
                total += int(m)
            except ValueError:
                total += 1
        out[key] = total
    return out


def pipeline_runtime_min(log_path: Path) -> float | None:
    """Extract today's daily run wall-clock from the log's start/end markers."""
    if not log_path.exists():
        return None
    text = ""
    for enc in ("utf-8", "utf-16-le", "utf-16"):
        try:
            text = log_path.read_text(encoding=enc, errors="ignore")
            if text:
                break
        except (OSError, UnicodeDecodeError):
            continue
    starts = re.findall(r"Daily run started.*?(\d{2}):(\d{2}):(\d{2})", text)
    ends = re.findall(r"Daily run done.*?(\d{2}):(\d{2}):(\d{2})", text)
    if not starts or not ends:
        return None
    h1, m1, s1 = map(int, starts[-1])
    h2, m2, s2 = map(int, ends[-1])
    return ((h2 * 3600 + m2 * 60 + s2) - (h1 * 3600 + m1 * 60 + s1)) / 60.0


# ── Render ───────────────────────────────────────────────────────────


def _row_key(r: dict) -> tuple[str, str]:
    return ((r.get("County") or "").strip(), (r.get("Case No.") or "").strip().upper())


def compute_diffs(today_rows: list[dict], yesterday_rows: list[dict]) -> dict:
    """Compare two polished CSVs (same week, different runs).

    Returns dict with: new, dropped, parcel_changed, reason_today.
    - new:            rows in today but not yesterday
    - dropped:        rows in yesterday but not today (regression signal —
                      polish dropped something it had before)
    - parcel_changed: rows present in both but with a different Parcel ID
    - reason_today:   Counter of Match Reason tags from today's run
    """
    by_yest = {_row_key(r): r for r in yesterday_rows}
    by_today = {_row_key(r): r for r in today_rows}

    new = [r for k, r in by_today.items() if k not in by_yest]
    dropped = [r for k, r in by_yest.items() if k not in by_today]

    parcel_changed: list[dict] = []
    for k, r_today in by_today.items():
        r_yest = by_yest.get(k)
        if r_yest is None:
            continue
        p_y = (r_yest.get("Parcel ID") or "").strip()
        p_t = (r_today.get("Parcel ID") or "").strip()
        if p_y and p_t and p_y != p_t:
            parcel_changed.append({
                "case_no": r_today.get("Case No.", ""),
                "county":  r_today.get("County", ""),
                "decedent": r_today.get("Deceased Owner", ""),
                "parcel_yesterday": p_y,
                "parcel_today":     p_t,
                "addr_yesterday":   (r_yest.get("Property Address") or "").strip(),
                "addr_today":       (r_today.get("Property Address") or "").strip(),
            })

    reason_today: Counter[str] = Counter()
    for r in today_rows:
        raw = (r.get("Match Reason") or "").strip()
        if not raw:
            reason_today["(scrape direct)"] += 1
            continue
        for tag in (t.strip() for t in raw.split("|") if t.strip()):
            reason_today[tag] += 1

    return {
        "new": new,
        "dropped": dropped,
        "parcel_changed": parcel_changed,
        "reason_today": reason_today,
    }


def render_report(
    workbook_path: Path | None,
    workbook_rows: list[dict],
    week_n: int,
    today_csv_rows: list[dict],
    yesterday_csv_rows: list[dict],
    heir_transfer_rows: list[dict],
    polish_stats: dict,
    runtime_min: float | None,
) -> str:
    today_str = date.today().strftime("%a %b %d, %Y")
    diffs = compute_diffs(today_csv_rows, yesterday_csv_rows)
    new_today = diffs["new"]

    # Headlines
    total = len(workbook_rows)

    counties = Counter((r.get("County") or "").strip() for r in workbook_rows)

    lines: list[str] = []
    lines.append(f"NC Probate Pipeline — Daily Report")
    lines.append(f"  {today_str}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("HEADLINES")
    lines.append(f"  Workbook:           {workbook_path.name if workbook_path else '(missing!)'}")
    lines.append(f"  Total cases:        {total}")
    lines.append(f"  New today:          {len(new_today)}")
    if runtime_min is not None:
        lines.append(f"  Pipeline runtime:   {runtime_min:.0f} min")
    lines.append("")
    lines.append(f"  By county:")
    for c, n in counties.most_common():
        label = c if c else "(blank)"
        lines.append(f"    {label:14} {n}")
    lines.append("")

    # New cases
    lines.append("NEW CASES TODAY")
    if not new_today:
        lines.append("  (none — workbook unchanged)")
    else:
        for r in new_today[:50]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            prop = (r.get("Property Address") or "(no parcel)").strip()
            lines.append(f"  {cn:18}  {cty:12}  {dec[:32]:32}  ->  {prop}")
        if len(new_today) > 50:
            lines.append(f"  ... and {len(new_today) - 50} more")
    lines.append("")

    # Dropped since yesterday — regression signal. A case that was here
    # yesterday and isn't now means a polish step removed it. Could be a
    # legitimate drop (newly-failed audit, newly-detected heir-occupied)
    # or a regression to investigate.
    dropped = diffs["dropped"]
    lines.append("DROPPED SINCE YESTERDAY")
    if not dropped:
        lines.append("  (none)")
    else:
        for r in dropped[:25]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            prop = (r.get("Property Address") or "(no parcel)").strip()
            lines.append(f"  {cn:18}  {cty:12}  {dec[:32]:32}  ->  {prop}")
        if len(dropped) > 25:
            lines.append(f"  ... and {len(dropped) - 25} more")
    lines.append("")

    # Parcel changed since yesterday — same case, different parcel now.
    # Usually a smart-picker repick or a new sibling found a better main.
    pc = diffs["parcel_changed"]
    lines.append("PARCEL CHANGED SINCE YESTERDAY")
    if not pc:
        lines.append("  (none)")
    else:
        for e in pc[:15]:
            lines.append(f"  {e['case_no']:18}  {e['county']:12}  {e['decedent'][:30]:30}")
            lines.append(f"    was: {e['parcel_yesterday']:18}  {e['addr_yesterday']}")
            lines.append(f"    now: {e['parcel_today']:18}  {e['addr_today']}")
        if len(pc) > 15:
            lines.append(f"  ... and {len(pc) - 15} more")
    lines.append("")

    # Heir-transfer
    lines.append("HEIR-TRANSFER FLAGS (review file)")
    if not heir_transfer_rows:
        lines.append("  (none flagged)")
    else:
        # Count unique decedents
        unique_decedents = {(r.get("County"), r.get("Case No.")) for r in heir_transfer_rows}
        lines.append(f"  {len(unique_decedents)} decedent(s) with {len(heir_transfer_rows)} candidate parcel(s) flagged")
        # Top 5 highest-acreage rows (proxy for "biggest lead")
        # Heir-transfer XLSX may not have acreage; just show first 5 by case
        # Group by case
        by_case: dict[tuple, list[dict]] = {}
        for r in heir_transfer_rows:
            key = (r.get("County"), r.get("Case No."), r.get("Deceased Owner"))
            by_case.setdefault(key, []).append(r)
        for (cty, cn, dec), cands in list(by_case.items())[:5]:
            lines.append(f"  {cn}  {cty}  {dec}  ({len(cands)} candidate parcels)")
        if len(by_case) > 5:
            lines.append(f"  ... and {len(by_case) - 5} more decedents")
    lines.append("")

    # Polish drops
    lines.append("POLISH DROPS")
    drop_labels = [
        ("over_500k",     "Over $500K (buy-box cap)"),
        ("heir_occupied", "Heir-occupied (PR mailing = property)"),
        ("commercial",    "Commercial/industrial"),
        ("no_parcel",     "No parcel found in county GIS"),
        ("archive_dupe",  "Cross-week archive duplicate"),
        ("non_pending",   "Case status not Pending"),
    ]
    any_drops = False
    for key, label in drop_labels:
        n = polish_stats.get(key, 0)
        if n:
            lines.append(f"  {label:40} {n}")
            any_drops = True
    if not any_drops:
        lines.append("  (no drops recorded)")
    if polish_stats.get("repick"):
        lines.append(f"  Smart-picker REPICK events:               {polish_stats['repick']}")
    if polish_stats.get("refound"):
        lines.append(f"  Step 0.5 Re-found correct parcels:        {polish_stats['refound']}")
    lines.append("")

    # Match Reason distribution — how each kept row got to its current state.
    # (scrape direct) = parcel + PR from court directly (high confidence,
    # no polish-step fallback fired). Other tags name the fallback step.
    reason_today = diffs["reason_today"]
    lines.append("MATCH REASON DISTRIBUTION (today's polished output)")
    if not reason_today:
        lines.append("  (no rows in today's CSV)")
    else:
        for tag, n in reason_today.most_common():
            lines.append(f"  {tag:30} {n}")
    lines.append("")

    lines.append("=" * 60)
    lines.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


# ── Email ────────────────────────────────────────────────────────────


def _send_email_resend(
    subject: str, body: str, attachments: list[Path] | None = None,
) -> tuple[bool, str]:
    """Send via Resend HTTP API. Used when RESEND_API_KEY is in .env."""
    import base64
    import requests

    api_key = os.environ["RESEND_API_KEY"]
    sender = os.environ.get("REPORT_FROM", "reports@remedihomesolutions.com")
    recipients_raw = os.environ.get("REPORT_TO", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        return False, "REPORT_TO not set in .env"

    payload: dict = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "text": body,
    }

    if attachments:
        attached = []
        for att in attachments:
            if not att.exists():
                continue
            attached.append({
                "filename": att.name,
                "content": base64.b64encode(att.read_bytes()).decode("ascii"),
            })
        if attached:
            payload["attachments"] = attached

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    except requests.RequestException as e:
        return False, f"Resend HTTP error: {type(e).__name__}: {e}"
    if r.status_code >= 300:
        return False, f"Resend rejected (HTTP {r.status_code}): {r.text[:300]}"
    return True, f"Sent via Resend to {', '.join(recipients)} (id={r.json().get('id', '?')})"


def _send_email_smtp(
    subject: str, body: str, attachments: list[Path] | None = None,
) -> tuple[bool, str]:
    """Fallback: send via Gmail/Workspace SMTP using app password."""
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    report_to = os.environ.get("REPORT_TO") or smtp_user
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    if not smtp_user or not smtp_pass:
        return False, "Neither RESEND_API_KEY nor SMTP_USER/SMTP_PASS set in .env — skipping email."

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = report_to
    msg["Subject"] = subject
    msg.set_content(body)

    for att in attachments or []:
        if not att.exists():
            continue
        ctype = "application/octet-stream"
        if att.suffix.lower() == ".xlsx":
            ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        maintype, subtype = ctype.split("/", 1)
        with att.open("rb") as fp:
            msg.add_attachment(fp.read(), maintype=maintype, subtype=subtype, filename=att.name)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Gmail rejected the app password: {e}. Re-generate at https://myaccount.google.com/apppasswords"
    except Exception as e:
        return False, f"Email send failed: {type(e).__name__}: {e}"
    return True, f"Sent via SMTP to {report_to}"


def send_email(subject: str, body: str, attachments: list[Path] | None = None) -> tuple[bool, str]:
    """Send via Resend if RESEND_API_KEY is set, else fall back to SMTP."""
    if os.environ.get("RESEND_API_KEY"):
        return _send_email_resend(subject, body, attachments=attachments)
    return _send_email_smtp(subject, body, attachments=attachments)


def _count_new_cases(today_rows: list[dict], yesterday_rows: list[dict]) -> int:
    """Cases in today's polished CSV that weren't in yesterday's."""
    def key(r):
        return ((r.get("County") or "").strip(), (r.get("Case No.") or "").strip().upper())
    yesterday = {key(r) for r in yesterday_rows}
    return sum(1 for r in today_rows if key(r) not in yesterday)


# ── Main ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true", help="Skip the email send (file output only)")
    ap.add_argument("--attach-workbook", action="store_true", help="Attach the FTM workbook to the email")
    args = ap.parse_args(argv)

    wb_path = find_latest_workbook()
    if not wb_path:
        print("ERROR: no FTM workbook found in output/", file=sys.stderr)
        return 1
    week_n, workbook_rows = read_workbook_cases(wb_path)

    today_datasift = find_latest_datasift(week_n)
    today_rows = read_csv_cases(today_datasift) if today_datasift else []
    yesterday_datasift = find_yesterdays_datasift(week_n, today_datasift) if today_datasift else None
    yesterday_rows = read_csv_cases(yesterday_datasift) if yesterday_datasift else []

    heir_path = find_latest_heir_transfer(week_n)
    heir_rows = read_heir_transfer(heir_path)

    polish_log = LOGS / "nc_daily_run.log"
    polish_stats = parse_polish_log(polish_log)
    runtime = pipeline_runtime_min(polish_log)

    report = render_report(
        workbook_path=wb_path,
        workbook_rows=workbook_rows,
        week_n=week_n,
        today_csv_rows=today_rows,
        yesterday_csv_rows=yesterday_rows,
        heir_transfer_rows=heir_rows,
        polish_stats=polish_stats,
        runtime_min=runtime,
    )

    out_path = OUTPUT / f"daily_report_{date.today().strftime('%Y-%m-%d')}.txt"
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    print()
    print(report)

    if args.no_email:
        return 0

    attachments = [out_path]
    if heir_path:
        attachments.append(heir_path)
    if args.attach_workbook:
        attachments.append(wb_path)

    new_count = _count_new_cases(today_rows, yesterday_rows)
    subject = f"NC Probate Daily — Week {week_n} — {new_count} new"
    ok, msg = send_email(subject, report, attachments=attachments)
    print(f"\nEmail: {msg}")
    return 0 if ok else 0  # File was written; email is best-effort


if __name__ == "__main__":
    sys.exit(main())
