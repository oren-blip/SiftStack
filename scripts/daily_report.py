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
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
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
# Running deep-prospecting ledger (repo root, committed). Every DP run —
# whether it produced a research doc or just an address/phone fix — appends a
# row here; the report's DEEP PROSPECTING section reads it (Oren, 2026-08-12).
DP_LOG = Path("dp_log.csv")


def read_dp_log() -> list[dict]:
    if not DP_LOG.exists():
        return []
    try:
        with DP_LOG.open(newline="", encoding="utf-8-sig") as f:
            return [r for r in csv.DictReader(f) if (r.get("Case No.") or "").strip()]
    except OSError:
        return []


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
    # Real events print "REPICK {county}/{decedent}: ..." — require the slash so
    # the report's own "Smart-picker REPICK events: N" line (the report text is
    # echoed into nc_daily_run.log by the nightly bat) doesn't count itself.
    "repick":        re.compile(r"REPICK \S+/"),
    "refound":       re.compile(r"Re-found correct parcels: (\d+)"),
    "under_min_value": re.compile(r"Dropped under-min-value: (\d+)"),
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
    # Only accept a done marker AFTER the last start — a deadline-killed run
    # never prints one, and pairing it with an older run's end fabricates a
    # plausible-looking but bogus runtime.
    last_start = text.rfind("Daily run started")
    ends = re.findall(r"Daily run done.*?(\d{2}):(\d{2}):(\d{2})",
                      text[last_start:]) if last_start >= 0 else []
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


# One-line plain-English description per Match Reason tag, shown as a glossary
# under the distribution and appended inline to each line. Dynamic-suffix tags
# (lot-cluster-N, low-confidence-parcel(NN%)) are matched by prefix in
# _describe_reason(). Keep in sync with tag_reason() calls in fix_addresses_and_prep.py.
REASON_GLOSSARY: dict[str, str] = {
    "(scrape direct)": "Parcel + PR came straight from the court record — no guessing",
    "default-sfr": "Property type unknown — labeled Single-Family (safe default)",
    "addr-corrected": "Property street address fixed/standardized from county records",
    "centroid-geocode": "No exact street number — map pin placed at the parcel's center",
    "name-research": "Property found by searching county records for the deceased's name",
    "name-nearmiss-addr-corroborated": "Name wasn't exact but the address confirmed it — treated as solid",
    "decedent-address": "Property matched using the deceased's own address from the court file",
    "app-realestate-parcel": "Parcel read from the real-estate section of the court Application PDF",
    "collapsed-same-property": "Duplicate rows for the same property merged into one",
    "condo-overruled-by-zillow": "Zillow says it's a house, not a condo — kept",
    "lincoln-ahdesc-structure": "Lincoln County structure type read from the GIS description field",
    # --- flagged: the matcher made a call but isn't fully sure (eyeball) ---
    "verify-middle-initial": "Matched via middle initial to separate same-named people — double-check",
    "verify-name-nomiddle": "Name matched but deed had no middle name to confirm — eyeball",
    "verify-name-ambiguous": "Several people could fit the name — best guess, eyeball",
    "verify-swap-lowconf": "Parcel swapped in with low confidence — eyeball",
    "verify-swap-ambiguous": "Parcel swap was ambiguous — eyeball",
    "low-confidence-parcel": "Property match scored below the 'strong' bar — eyeball",
    "addr-uncorroborated": "Address applied but not independently confirmed — eyeball",
    "verify-occupied-confirmed": "Court-confirmed home the surviving spouse occupies — kept (locked)",
    # --- multi-parcel / land ---
    "lot-cluster": "Estate with adjacent lots on one street — mobile-home-on-land play",
    "swap-on-dq": "Main property disqualified (e.g. heir lives there) — mailed a different estate parcel",
    "swap-on-over-cap": "Main house over your $500K cap — points to an under-cap estate parcel",
    "subdivide-exempt": "SFR/MH on >2 acres — gets the $1M cap (land is the play)",
    "tiny-vacant-lot": "Small vacant lot (low standalone value)",
    # --- where the contact / PR came from ---
    "heirs-of-fallback": "No usable PR/beneficiary — contact defaults to 'Heirs of [Deceased]' (deep-prospecting)",
    "coowner-dm": "Contact taken from a co-owner on the deed",
    "coowner-address": "Mailing address taken from a co-owner on the deed",
    "dm-promoted-pr": "No court executor — the obituary-found living heir (a real person) was promoted to mail target",
    "beneficiary-promoted-pr": "No court executor + no obit heir — a named beneficiary (real person w/ address) was promoted to mail target",
    "beneficiary-address": "Mailing address taken from a named beneficiary",
    "pr-backfill-parties": "PR filled from the eCourts Parties list",
    "pr-from-app-over-obit": "PR taken from the court Application, overriding a weaker obituary guess",
    "pr-from-app-override": "PR taken from the court Application, overriding another source",
    "pr-people-search": "PR's address found via free people-search",
    "pr-tracerfy": "PR's contact found via Tracerfy skip trace",
    "tracerfy": "Contact found via Tracerfy skip trace",
    "mailing-from-property": "PR mailing filled from the property address (so mail still lands)",
    "mailing-from-prior-main": "PR mailing kept at the estate home the main parcel was swapped away from",
    "mailing-addr-split": "Mailing address split out of a combined field",
    "second-pass-obit-full": "Heir/PR found on a second obituary pass (full-name match)",
    "second-pass-obit-name-only": "Heir/PR found on a second obituary pass (name-only match)",
    # --- case data / values ---
    "landportal-revalued": "Vacant lot's value filled from the LandPortal data source",
    "late-doc-apply": "A court document arrived late — its info was applied",
    "small-estate-disposed-recent": "Recently-filed small-estate/disposed case (you work these)",
    "small-estate-address": "Property address from a small-estate filing",
    "heir-transferred-deed": "Deed already moved to a next-gen heir — still a lead, flagged",
    "dq-recently-sold": "Flagged — the property sold recently",
    "rowan-condo": "Rowan County condo (flagged — condos are normally dropped)",
    "audit-repick": "Nightly audit re-picked a better parcel for this case",
    "audit-blanked": "Nightly audit removed a parcel that no longer passes the matcher",
    "pdf-phone": "Phone number pulled from the court PDF",
    "pdf-phone-verified": "Phone number pulled from the court PDF and cross-checked",
}

# Tags meaning "matched, but not fully sure" — summed into the 'Cases to eyeball'
# headline. Matched by prefix so dynamic-suffix variants are included.
_EYEBALL_PREFIXES = (
    "verify-middle-initial", "verify-name-nomiddle", "verify-name-ambiguous",
    "verify-swap-lowconf", "verify-swap-ambiguous",
    "low-confidence-parcel", "addr-uncorroborated",
)


def _describe_reason(tag: str) -> str:
    """Plain-English one-liner for a Match Reason tag (handles dynamic suffixes)."""
    if tag in REASON_GLOSSARY:
        return REASON_GLOSSARY[tag]
    for key, desc in REASON_GLOSSARY.items():
        if tag.startswith(key):
            return desc
    return ""


def _is_eyeball_reason(tag: str) -> bool:
    """True if the tag means the matcher made an uncertain call worth a glance."""
    return any(tag.startswith(p) for p in _EYEBALL_PREFIXES)


def _tab_week(r: dict) -> int:
    """ISO week number of the workbook tab a row came from (0 if unknown)."""
    m = re.search(r"Week (\d+)", str(r.get("_tab") or ""))
    return int(m.group(1)) if m else 0


def _is_heirs_of(r: dict) -> bool:
    return (r.get("Personal Representative") or "").strip().lower().startswith("heirs of")


def _has_named_contact(r: dict) -> bool:
    name = ((r.get("First Name") or "") + (r.get("Last Name") or "")).strip() \
        or (r.get("Personal Representative") or "").strip()
    return bool(name) and not _is_heirs_of(r)


def _has_phone(r: dict) -> bool:
    return bool((r.get("Phone 1") or "").strip() or (r.get("DM Phone") or "").strip())


def eyeball_cases(rows: list[dict]) -> list[tuple[dict, list[str]]]:
    """Rows whose Match Reason carries at least one uncertain (eyeball) tag."""
    out: list[tuple[dict, list[str]]] = []
    for r in rows:
        tags = [t.strip() for t in (r.get("Match Reason") or "").split("|") if t.strip()]
        eye = [t for t in tags if _is_eyeball_reason(t)]
        if eye:
            out.append((r, eye))
    return out


def _why(tag: str) -> str:
    """Glossary description with the trailing '— eyeball'-style nag stripped
    (the section these lines appear in already says they need a look)."""
    desc = _describe_reason(tag) or tag
    head, sep, tail = desc.rpartition("—")
    if sep and ("eyeball" in tail or "double-check" in tail):
        return head.strip()
    return desc


def get_stale_docs() -> list[dict]:
    """High-priority cases whose court docs still aren't scanned (21+ days)."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        import case_doc_queue as _cdq  # noqa: E402
        from ecourts_scraper import cases_needing_docs as _cnd  # noqa: E402
        return _cdq.long_pending_high_priority(set(_cnd()), min_age_days=21)
    except Exception:
        return []


def get_late_doc_updates() -> list[dict]:
    """Archived-week rows that just got a real named contact (last 7 days)."""
    try:
        import json as _json
        entries = _json.loads((OUTPUT / ".late_doc_updates.json")
                              .read_text(encoding="utf-8")).get("entries", [])
        cut = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
        return [e for e in entries if e.get("found_iso", "") >= cut]
    except Exception:
        return []


def _cases_preview(rows: list[dict], key: str, n: int = 3) -> str:
    """First n case numbers as a comma string — Oren looks cases up by number."""
    cases = [c for c in ((r.get(key) or "").strip() for r in rows) if c][:n]
    out = ", ".join(cases)
    if len(rows) > n:
        out += f" (+{len(rows) - n} more)"
    return out


def tracerfy_budget_line() -> str:
    """This week's Tracerfy burn vs cap, or '' if unavailable/unfunded."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from tracerfy_budget import budget_summary  # noqa: E402
        return budget_summary() or ""
    except Exception:
        return ""


def summarize_week_improvements(monday: date) -> list[str]:
    """Plain-English bullets describing the week's pipeline improvements.

    Reads this week's commit subjects + bodies and asks Haiku to group them
    into a few non-technical bullets ("what changed and why it matters").
    Disk-cached on the commit-set hash, so it costs at most ONE small call
    per night (standing directive: keep LLM cost very low). Returns [] when
    git/LLM is unavailable — callers fall back to raw commit subjects.
    """
    try:
        r = subprocess.run(
            ["git", "log", f"--since={monday.isoformat()} 00:00", "--no-merges",
             "--pretty=%h%x1f%s%x1f%b%x1e"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent))
        raw = r.stdout if r.returncode == 0 else ""
    except Exception:
        raw = ""
    commits: list[tuple[str, str, str]] = []
    for chunk in raw.split("\x1e"):
        parts = chunk.strip("\n").split("\x1f")
        if len(parts) >= 2 and parts[0].strip():
            body = parts[2].strip() if len(parts) > 2 else ""
            commits.append((parts[0].strip(), parts[1].strip(), body))
    if not commits:
        return []

    import hashlib
    import json as _json
    key = hashlib.sha1("|".join(h for h, _, _ in commits).encode()).hexdigest()
    cache_path = OUTPUT / ".report_changes_cache.json"
    try:
        cached = _json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("key") == key and cached.get("bullets"):
            return list(cached["bullets"])
    except Exception:
        pass

    commit_lines = []
    for _h, subj, body in commits[:30]:
        first_para = body.split("\n\n")[0].replace("\n", " ").strip()[:400]
        commit_lines.append(f"- {subj}" + (f" :: {first_para}" if first_para else ""))
    prompt = (
        "You write the \"what improved this week\" section of a nightly status "
        "email for Oren, a solo real-estate investor whose automated pipeline "
        "finds probate leads and preps them for direct mail and cold calls.\n\n"
        "This week's code changes (subject :: details):\n"
        + "\n".join(commit_lines)
        + "\n\nRewrite as 3-7 short bullets. Group related changes into one "
        "bullet. Each bullet says what changed and why it matters to his "
        "leads, mail, or calls — in plain English a non-programmer gets. "
        "No file names, no jargon, no commit hashes. Most impactful first.\n\n"
        'Return JSON only: {"bullets": ["...", "..."]}'
    )
    bullets: list[str] = []
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        import llm_client  # noqa: E402
        resp = llm_client.chat_json(prompt, max_tokens=700)
        if resp and isinstance(resp.get("bullets"), list):
            bullets = [str(b).strip() for b in resp["bullets"] if str(b).strip()][:8]
    except Exception:
        bullets = []
    if not bullets:
        return []
    try:
        cache_path.write_text(_json.dumps({"key": key, "bullets": bullets}),
                              encoding="utf-8")
    except OSError:
        pass
    return bullets


def git_fixes_since(day: date) -> list[str]:
    """Commit subjects since `day` — the week's pipeline work, for the
    'what got done' section. 'Ddd<TAB>subject' lines; [] if git unavailable."""
    try:
        r = subprocess.run(
            ["git", "log", f"--since={day.isoformat()} 00:00", "--no-merges",
             "--pretty=%cd\t%s", "--date=format:%a"],
            capture_output=True, text=True, timeout=15,
            cwd=str(Path(__file__).parent.parent))
        if r.returncode != 0:
            return []
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def datasift_upload_status(rows: list[dict]) -> tuple[int, int]:
    """(already uploaded, awaiting upload) for this week's rows, from the
    NETNEW upload ledger. (-1, -1) if the ledger can't be read."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from nc_datasift_export import load_upload_ledger  # noqa: E402
        ledger = load_upload_ledger()
    except Exception:
        return -1, -1
    in_ds = sum(1 for r in rows
                if (r.get("Case No.") or "").strip().upper() in ledger)
    return in_ds, len(rows) - in_ds


def render_report(
    workbook_path: Path | None,
    workbook_rows: list[dict],
    week_n: int,
    today_csv_rows: list[dict],
    yesterday_csv_rows: list[dict],
    heir_transfer_rows: list[dict],
    polish_stats: dict,
    runtime_min: float | None,
    include_heir_transfer: bool = False,
    condensed: bool = False,
    improvements: list[str] | None = None,
) -> str:
    """Render the report. condensed=True builds the short email body (the
    most important items only, with a pointer to the attached full report);
    condensed=False builds the full .txt with every fine-print section."""
    today = date.today()
    today_str = today.strftime("%a %b %d, %Y")
    wd = today.weekday()
    day_note = f"court day {wd + 1} of 5" if wd < 5 else "weekend catch-up run"
    monday = today - timedelta(days=wd)
    diffs = compute_diffs(today_csv_rows, yesterday_csv_rows)
    new_today = diffs["new"]

    # Weekly lens (Oren, 2026-08-14): the current week's polished CSV IS this
    # week's inventory — lead with it, demote day-to-day churn and plumbing.
    week_rows = today_csv_rows
    this_week_total = len(week_rows)
    wk_counts = Counter(_tab_week(r) for r in workbook_rows)
    wk_counts.pop(0, None)
    prev_weeks = sorted(w for w in wk_counts if w < week_n)
    prev_week = prev_weeks[-1] if prev_weeks else None
    prev_total = wk_counts.get(prev_week, 0) if prev_week is not None else 0

    ready = [r for r in week_rows
             if _has_named_contact(r) and (r.get("Property Address") or "").strip()]
    with_phone = [r for r in week_rows if _has_phone(r)]
    heirs_of = [r for r in week_rows if _is_heirs_of(r)]
    eyeballs = eyeball_cases(week_rows)
    in_ds, awaiting = datasift_upload_status(week_rows)

    lines: list[str] = []
    lines.append(f"NC Probate Pipeline — Week {week_n}")
    lines.append(f"  {today_str} — {day_note}")
    lines.append("=" * 60)
    lines.append("")

    lines.append("THIS WEEK AT A GLANCE")
    cmp_note = f"    (Week {prev_week} finished at {prev_total})" if prev_week else ""
    lines.append(f"  Cases this week:      {this_week_total}{cmp_note}")
    lines.append(f"  Added today:          {len(new_today)}")
    lines.append(f"  Ready to work:        {len(ready)}    have a property + a named person to contact")
    # Phones mostly arrive AFTER upload (DataSift skip trace) — only show the
    # in-CSV count when deep prospecting actually put numbers on rows, so a 0
    # here doesn't read as "no phones anywhere".
    if with_phone:
        lines.append(f"  Have a phone number:  {len(with_phone)}    (from court docs / deep prospecting)")
    lines.append(f"  \"Heirs of\" rows:      {len(heirs_of)}    no named contact yet — deep-prospecting queue")
    lines.append(f"  Check these:          {len(eyeballs)}    uncertain matches — listed below")
    if in_ds >= 0:
        lines.append(f"  In DataSift already:  {in_ds}    ({awaiting} waiting for the next upload)")
    lines.append("")
    county_this = Counter((r.get("County") or "").strip() for r in week_rows)
    county_prev = Counter((r.get("County") or "").strip() for r in workbook_rows
                          if prev_week is not None and _tab_week(r) == prev_week)
    lines.append("  By county:           this wk   last wk")
    for c, _n in county_this.most_common():
        label = c if c else "(blank)"
        lines.append(f"    {label:16} {county_this.get(c, 0):>7}   {county_prev.get(c, 0):>7}")
    for c in sorted(set(county_prev) - set(county_this)):
        label = c if c else "(blank)"
        lines.append(f"    {label:16} {0:>7}   {county_prev[c]:>7}")
    lines.append("")

    # A county GIS that went down during the polish. Its rows lost their parcel
    # to a dead server (not to "owns nothing") and were dropped at Step 4 — so
    # tonight's sheet is short for that county. The next clean run restores them,
    # and auto_archive_weeks.py won't freeze the week until then; this is just so
    # a short county count doesn't read as a quiet week.
    try:
        import json as _json
        _o = _json.loads((Path("output") / ".gis_outage_last_run.json")
                         .read_text(encoding="utf-8"))
        if _o.get("counties"):
            lines.append("*** COUNTY GIS OUTAGE THIS RUN ***")
            lines.append(f"  Down: {', '.join(_o['counties'])}")
            lines.append(f"  Rows for these counties are INCOMPLETE in week(s) "
                         f"{_o.get('weeks', [])} — they will be recovered on the "
                         f"next clean run, and the week won't be archived until then.")
            lines.append("")
    except Exception:
        pass

    # What to work on next — the priority queue, ranked. Hand-entry work that
    # nothing else surfaces comes first; volume queues last. Only non-empty
    # items get a number; case numbers up front (Oren looks cases up by number).
    dp_rows = read_dp_log()
    open_dp = [r for r in dp_rows if (r.get("Outcome") or "").strip() == "open"]
    stale_docs = get_stale_docs()
    late_docs = get_late_doc_updates()
    prios: list[str] = []
    if late_docs:
        prios.append("Type these into DataSift by hand — archived cases just got a "
                     f"named contact: {_cases_preview(late_docs, 'case_number')}")
    if stale_docs:
        prios.append("Next courthouse trip — pull the unscanned docs for: "
                     f"{_cases_preview(stale_docs, 'case_number')}")
    if eyeballs:
        prios.append(f"Double-check {len(eyeballs)} uncertain matches before "
                     "mailing (worst listed below)")
    if open_dp:
        prios.append(f"Finish {len(open_dp)} open deep-prospecting case(s): "
                     f"{_cases_preview(open_dp, 'Case No.')}")
    if in_ds >= 0 and awaiting > 0:
        prios.append(f"{awaiting} polished rows are waiting for the next DataSift upload")
    if heirs_of:
        prios.append(f'{len(heirs_of)} "Heirs of" rows still need a named contact '
                     "(deep-prospecting queue)")
    lines.append("WHAT TO WORK ON NEXT")
    if not prios:
        lines.append("  (nothing urgent — pipeline is clean)")
    for i, p in enumerate(prios, 1):
        lines.append(f"  {i}. {p}")
    lines.append("")

    # What got done — the week's progress in plain terms: cases in, contacts
    # found, deep-prospecting worked by hand, pipeline fixes shipped (git).
    monday_iso = monday.isoformat()
    dp_resolved_wk = [r for r in dp_rows
                      if (r.get("Date") or "") >= monday_iso
                      and (r.get("Outcome") or "").strip() in ("resolved", "partial")]
    fixes = git_fixes_since(monday)
    lines.append(f"WHAT GOT DONE THIS WEEK (since Mon {monday.strftime('%b %d')})")
    lines.append(f"  {this_week_total} new estate cases found and matched to property")
    phone_note = f"; {len(with_phone)} already have a phone number" if with_phone else ""
    lines.append(f"  {len(ready)} are mail-ready with a named contact{phone_note}")
    if dp_resolved_wk:
        if condensed:
            lines.append(f"  {len(dp_resolved_wk)} deep-prospecting cases worked by "
                         "hand (case detail in the attached report)")
        else:
            lines.append(f"  {len(dp_resolved_wk)} deep-prospecting cases worked by hand:")
            for r in dp_resolved_wk:
                note = (r.get("Notes") or "").strip().replace("\n", " ")
                lines.append(f"    {r.get('Case No.',''):16}  {(r.get('Decedent') or '')[:24]:24}  {note[:64]}")
    # Improvements: plain-English grouped bullets (LLM, cached) when available;
    # raw commit subjects otherwise. The full report also keeps the commit list
    # underneath as the audit trail.
    import textwrap
    if improvements:
        lines.append("  Pipeline improvements this week — what changed and why it matters:")
        for b in improvements:
            for j, seg in enumerate(textwrap.wrap(b, width=86)):
                lines.append(f"    {'*' if j == 0 else ' '} {seg}")
    if fixes and (not condensed or not improvements):
        n_show = 6 if condensed else 15
        lines.append(f"  {len(fixes)} commit(s) shipped:")
        for fx in fixes[:n_show]:
            day_abbr, _, subj = fx.partition("\t")
            lines.append(f"    {day_abbr:4} {subj[:90]}")
        if len(fixes) > n_show:
            lines.append(f"    ... and {len(fixes) - n_show} more")
    lines.append("")

    # New cases
    lines.append("NEW CASES TODAY")
    n_new_cap = 15 if condensed else 50
    if not new_today:
        lines.append("  (none — workbook unchanged)")
    else:
        for r in new_today[:n_new_cap]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            prop = (r.get("Property Address") or "(no parcel)").strip()
            lines.append(f"  {cn:18}  {cty:12}  {dec[:32]:32}  ->  {prop}")
        if len(new_today) > n_new_cap:
            lines.append(f"  ... and {len(new_today) - n_new_cap} more")
    lines.append("")

    # Uncertain matches — the actual rows (with Case No.), not just tag counts.
    # Condensed: one line per case (why inline, address left to the workbook).
    lines.append("CHECK THESE — UNCERTAIN MATCHES (this week)")
    if not eyeballs:
        lines.append("  (none — every match this week is solid)")
    elif condensed:
        lines.append("  (the matcher made a judgment call — worth a look before mailing)")
        for r, tags in eyeballs[:8]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            lines.append(f"  >> {cn:18}  {cty:12}  {dec[:24]:24}  {_why(tags[0])}")
        if len(eyeballs) > 8:
            lines.append(f"  ... and {len(eyeballs) - 8} more — full list in the attached report")
    else:
        lines.append("  (the matcher made a judgment call — worth a look before mailing)")
        for r, tags in eyeballs[:20]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            prop = (r.get("Property Address") or "(no parcel)").strip()
            lines.append(f"  >> {cn:18}  {cty:12}  {dec[:28]:28}  {prop}")
            for t in tags:
                lines.append(f"       why: {_why(t)}")
        if len(eyeballs) > 20:
            lines.append(f"  ... and {len(eyeballs) - 20} more — sort the workbook's Match Reason column")
    lines.append("")

    # Deep prospecting still open — the hand-work queue. The condensed email
    # already surfaces these in WHAT TO WORK ON NEXT; detail is full-report only.
    if not condensed:
        lines.append("DEEP PROSPECTING — STILL OPEN")
        if not open_dp:
            lines.append("  (nothing open)")
        else:
            for r in open_dp:
                lines.append(f"  {r.get('Case No.',''):16}  {(r.get('Decedent') or '')[:30]:30}  "
                             f"{(r.get('Notes') or '')[:60]}")
        if dp_rows:
            n_docs = len(list((OUTPUT / "reports").glob("DP_*.md")))
            by_outcome = Counter((r.get("Outcome") or "?").strip() for r in dp_rows)
            outcome_str = ", ".join(f"{n} {k}" for k, n in by_outcome.most_common())
            lines.append(f"  (ledger: {len(dp_rows)} runs, {n_docs} research docs — {outcome_str})")
        lines.append("")

    # Documents the court still hasn't scanned for high-priority leads. We retry
    # nightly for months, but if the Application/Will never appears the only way
    # to the executor name is a manual courthouse pull — surface the oldest so
    # Oren can grab them by hand.
    if stale_docs and not condensed:
        lines.append("DOCS NOT SCANNED — MANUAL COURTHOUSE PULL (high-priority, 21+ days)")
        for e in stale_docs[:15]:
            lines.append(f"  {e.get('case_number',''):18} {e.get('county',''):12} "
                         f"{e['age_days']:>3}d  needs {','.join(e.get('needs', []))}")
        if len(stale_docs) > 15:
            lines.append(f"  ... and {len(stale_docs) - 15} more")
        lines.append("")

    # Wills/Applications that landed for weeks already archived. apply_late_docs.py
    # writes the name onto the archived sheet, but an archived week is not in the
    # workbook — this report is the ONLY place Oren would ever learn a dead
    # "Heirs of" row turned into a real named contact. Nothing pushes these to
    # DataSift, so they need typing in by hand; keep the case no. front and centre.
    if late_docs and not condensed:
        lines.append("LATE DOCS — ARCHIVED WEEKS JUST GOT A NAME (add to DataSift by hand)")
        for e in late_docs:
            _rel = f" ({e['relationship']})" if e.get("relationship") else ""
            lines.append(f"  {e.get('case_number',''):18} {e.get('county',''):12} "
                         f"wk{e.get('week','?')}  {e.get('was','')} -> {e.get('now','')}{_rel}")
        lines.append("")

    # Day-to-day churn — one compact section (weekly lens). Dropped rows are
    # still the regression signal; parcel changes are usually a smart-picker
    # repick or a new sibling parcel winning main.
    dropped = diffs["dropped"]
    pc = diffs["parcel_changed"]
    n_drop_cap = 5 if condensed else 15
    n_pc_cap = 3 if condensed else 10
    lines.append("CHANGES SINCE YESTERDAY'S RUN")
    if not dropped and not pc:
        lines.append("  (steady — nothing dropped, no parcels changed)")
    if dropped:
        lines.append(f"  Dropped ({len(dropped)}) — in yesterday's sheet, gone tonight:")
        for r in dropped[:n_drop_cap]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            prop = (r.get("Property Address") or "(no parcel)").strip()
            lines.append(f"    {cn:18}  {cty:12}  {dec[:30]:30}  {prop}")
        if len(dropped) > n_drop_cap:
            lines.append(f"    ... and {len(dropped) - n_drop_cap} more")
    if pc:
        lines.append(f"  Parcel changed ({len(pc)}) — same case, different parcel picked:")
        for e in pc[:n_pc_cap]:
            lines.append(f"    {e['case_no']:18}  {e['county']:12}  {e['decedent'][:30]:30}")
            lines.append(f"      was: {e['parcel_yesterday']:18}  {e['addr_yesterday']}")
            lines.append(f"      now: {e['parcel_today']:18}  {e['addr_today']}")
        if len(pc) > n_pc_cap:
            lines.append(f"    ... and {len(pc) - n_pc_cap} more")
    lines.append("")

    # Week-over-week pace from the workbook tabs (current week still filling).
    lines.append("WEEK-OVER-WEEK PACE")
    recent_weeks = sorted(wk_counts)[-6:]
    max_n = max((wk_counts[w] for w in recent_weeks), default=1) or 1
    for w in recent_weeks:
        n = wk_counts[w]
        bar = "#" * max(1, round(n / max_n * 28))
        tail = "   <- in progress" if w == week_n else ""
        lines.append(f"  Week {w:<3} {n:>4}  {bar}{tail}")
    lines.append("")

    # Condensed email stops here: fold runtime, drop total, and Tracerfy burn
    # into a two-line footer that points at the attached full report.
    ts_line = tracerfy_budget_line()
    if condensed:
        total_drops = sum(polish_stats.get(k, 0) for k in (
            "over_500k", "under_min_value", "heir_occupied", "commercial",
            "no_parcel", "archive_dupe", "non_pending"))
        bits = []
        if runtime_min is not None:
            bits.append(f"runtime {runtime_min:.0f} min")
        bits.append(f"{total_drops} rows dropped by filters tonight")
        bits.append(f"workbook total {len(workbook_rows)} cases")
        lines.append("FINE PRINT")
        lines.append("  " + " / ".join(bits))
        if ts_line:
            lines.append(f"  {ts_line}")
        lines.append("  Full detail — match reasons, drop breakdown, DP ledger — "
                     "is in the attached report file")
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(lines)

    # Tracerfy spend (when funded). One-line summary of this week's burn
    # vs cap — useful for catching runaway costs before they hit the cap.
    if ts_line:
        lines.append("TRACERFY BUDGET")
        lines.append(f"  {ts_line}")
        lines.append("")

    # Heir-transfer — off by default (Oren, 2026-07-18). The review XLSX still
    # generates in output/; it's just no longer summarized here or emailed.
    # Re-enable with `daily_report.py --include-heir-transfer`.
    if include_heir_transfer:
        lines.append("HEIR-TRANSFER FLAGS (review file)")
        if not heir_transfer_rows:
            lines.append("  (none flagged)")
        else:
            # Count unique decedents
            unique_decedents = {(r.get("County"), r.get("Case No.")) for r in heir_transfer_rows}
            lines.append(f"  {len(unique_decedents)} decedent(s) with {len(heir_transfer_rows)} candidate parcel(s) flagged")
            # Group by case; show first 5
            by_case: dict[tuple, list[dict]] = {}
            for r in heir_transfer_rows:
                key = (r.get("County"), r.get("Case No."), r.get("Deceased Owner"))
                by_case.setdefault(key, []).append(r)
            for (cty, cn, dec), cands in list(by_case.items())[:5]:
                lines.append(f"  {cn}  {cty}  {dec}  ({len(cands)} candidate parcels)")
            if len(by_case) > 5:
                lines.append(f"  ... and {len(by_case) - 5} more decedents")
        lines.append("")

    # Fine print — plumbing numbers, scoped to tonight's run (parse_polish_log
    # is called with since=now so these aren't the all-history sums anymore).
    lines.append("TONIGHT'S RUN — FINE PRINT")
    lines.append(f"  Workbook:          {workbook_path.name if workbook_path else '(missing!)'}")
    lines.append(f"  All weeks total:   {len(workbook_rows)} cases")
    if runtime_min is not None:
        lines.append(f"  Runtime:           {runtime_min:.0f} min")
    drop_labels = [
        ("over_500k",       "Dropped — over $500K (buy-box cap)"),
        ("under_min_value", "Dropped — under $10K (scrap parcel)"),
        ("heir_occupied",   "Dropped — heir-occupied (PR mailing = property)"),
        ("commercial",      "Dropped — commercial/industrial"),
        ("no_parcel",       "Dropped — no parcel found in county GIS"),
        ("archive_dupe",    "Dropped — cross-week archive duplicate"),
        ("non_pending",     "Dropped — case no longer Pending"),
    ]
    for key, label in drop_labels:
        n = polish_stats.get(key, 0)
        if n:
            lines.append(f"  {label:48} {n}")
    if polish_stats.get("repick"):
        lines.append(f"  Smart-picker REPICK events:                      {polish_stats['repick']}")
    if polish_stats.get("refound"):
        lines.append(f"  Step 0.5 re-found correct parcels:               {polish_stats['refound']}")
    lines.append("")

    # Match Reason distribution — how each kept row got to its current state.
    # (scrape direct) = parcel + PR from court directly (high confidence,
    # no polish-step fallback fired). Other tags name the fallback step.
    reason_today = diffs["reason_today"]
    lines.append("HOW THIS WEEK'S ROWS WERE MATCHED (fine print)")
    lines.append("  (how each kept case got its property + contact — '>>' = worth an eyeball)")
    if not reason_today:
        lines.append("  (no rows in today's CSV)")
    else:
        for tag, n in reason_today.most_common():
            flag = ">>" if _is_eyeball_reason(tag) else "  "
            desc = _describe_reason(tag)
            lines.append(f"  {flag} {tag:30} {n:>4}   {desc}")
    lines.append("")

    lines.append("=" * 60)
    lines.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


# ── HTML email rendering ─────────────────────────────────────────────
# The plain-text report above stays the single source of truth for content;
# the HTML email wraps it in a branded shell (header + stat tiles + county
# chips) and syntax-highlights the body (section headers, >> eyeball rows,
# *** alerts). Email-safe: inline styles only, table layout, system fonts.

_GREEN = "#1b5e20"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _highlight_body(text: str) -> str:
    """Turn the plain-text report body into styled, monospace HTML lines.
    Drops the top title block and the trailing divider/Generated footer
    (both are rendered elsewhere in the shell)."""
    lines = text.split("\n")
    try:
        start = next(i for i, l in enumerate(lines)
                     if l.strip() == "THIS WEEK AT A GLANCE")
    except StopIteration:
        start = 0
    end = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if s and set(s) == {"="}:
            end = i
            break
    mono = ("font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace;"
            "font-size:12.5px;line-height:1.55;white-space:pre;padding:1px 12px;margin:0;")
    out: list[str] = []
    for ln in lines[start:end]:
        stripped = ln.strip()
        if not stripped:
            out.append('<div style="height:9px;line-height:9px">&nbsp;</div>')
            continue
        esc = _esc(ln)
        if ln.startswith("***"):
            out.append(f'<div style="{mono}color:#b91c1c;font-weight:700;'
                       f'background:#fef2f2;">{esc}</div>')
        elif ln[0] != " " and not ln.startswith("="):
            out.append(f'<div style="color:{_GREEN};font-weight:700;font-size:11.5px;'
                       f'letter-spacing:.5px;text-transform:uppercase;margin:16px 0 4px;'
                       f'padding:0 12px 5px;border-bottom:1px solid #e4e8eb;">{esc}</div>')
        elif stripped.startswith(">>"):
            out.append(f'<div style="{mono}background:#fff8e1;color:#7a5300;">{esc}</div>')
        elif stripped.startswith("why:"):
            out.append(f'<div style="{mono}color:#8a919a;">{esc}</div>')
        else:
            out.append(f'<div style="{mono}color:#3a3f45;">{esc}</div>')
    return "\n".join(out)


def _stat_tile(number, label, accent_bg, accent_fg) -> str:
    return (
        f'<td style="width:25%;padding:6px;" valign="top">'
        f'<div style="background:{accent_bg};border-radius:8px;padding:14px 12px;text-align:center;">'
        f'<div style="font-size:30px;font-weight:800;color:{accent_fg};line-height:1;">{number}</div>'
        f'<div style="font-size:10.5px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;'
        f'color:#6b7280;margin-top:6px;">{label}</div>'
        f'</div></td>'
    )


def render_html_email(text: str, *, this_week: int, new_count: int, ready: int,
                      eyeball_n: int, counties, week_n: int) -> str:
    d = date.today()
    date_str = d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")
    gen = next((l for l in reversed(text.split("\n")) if l.startswith("Generated ")), "")

    # Stat tiles — eyeball tile turns amber only when there's something to check.
    eye_bg, eye_fg = (("#fff8e1", "#b45309") if eyeball_n else ("#eef1f4", "#374151"))
    tiles = (
        _stat_tile(this_week, "This week", "#eef1f4", "#111827")
        + _stat_tile(new_count, "New today", "#e7f4ea", _GREEN)
        + _stat_tile(ready, "Ready to work", "#e7f4ea", _GREEN)
        + _stat_tile(eyeball_n, "To check", eye_bg, eye_fg)
    )

    chips = ""
    for name, n in counties:
        label = name if name else "(blank)"
        chips += (f'<span style="display:inline-block;background:#eef1f4;color:#374151;'
                  f'border-radius:12px;padding:3px 10px;margin:0 6px 6px 0;font-size:12px;">'
                  f'{_esc(label)}&nbsp;<b>{n}</b></span>')

    body_html = _highlight_body(text)

    return f"""\
<!doctype html><html><body style="margin:0;padding:0;background:#eef0f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef0f2;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="700" cellpadding="0" cellspacing="0" style="max-width:700px;width:100%;background:#ffffff;border:1px solid #e2e5e9;border-radius:12px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <tr><td style="background:{_GREEN};padding:22px 24px;">
    <div style="color:#ffffff;font-size:19px;font-weight:800;letter-spacing:.2px;">NC Probate Pipeline &middot; Week {week_n}</div>
    <div style="color:#bfe3c5;font-size:13px;margin-top:3px;">{date_str}</div>
  </td></tr>
  <tr><td style="padding:14px 18px 4px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{tiles}</tr></table>
  </td></tr>
  <tr><td style="padding:6px 24px 2px;">
    <div style="font-size:11px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;color:#6b7280;margin-bottom:8px;">By county &mdash; this week</div>
    <div>{chips}</div>
  </td></tr>
  <tr><td style="padding:8px 12px 4px;">
    <div style="overflow-x:auto;border:1px solid #eceef1;border-radius:8px;padding:8px 0;background:#fbfbfc;">
      {body_html}
    </div>
  </td></tr>
  <tr><td style="padding:12px 24px 22px;color:#9aa1a9;font-size:11px;">
    {_esc(gen)} &middot; SiftStack
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


# ── Email ────────────────────────────────────────────────────────────


def _send_email_resend(
    subject: str, body: str, attachments: list[Path] | None = None,
    html: str | None = None,
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
        "text": body,   # plain-text fallback for clients that don't render HTML
    }
    if html:
        payload["html"] = html

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
    html: str | None = None,
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
    msg.set_content(body)   # plain-text part
    if html:
        # multipart/alternative — clients pick HTML, fall back to text
        msg.add_alternative(html, subtype="html")

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


def send_email(subject: str, body: str, attachments: list[Path] | None = None,
               html: str | None = None) -> tuple[bool, str]:
    """Send via Resend if RESEND_API_KEY is set, else fall back to SMTP."""
    if os.environ.get("RESEND_API_KEY"):
        return _send_email_resend(subject, body, attachments=attachments, html=html)
    return _send_email_smtp(subject, body, attachments=attachments, html=html)


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
    ap.add_argument("--include-heir-transfer", action="store_true",
                    help="Re-enable the heir-transfer review section + XLSX attachment "
                         "(off by default per Oren; the XLSX still generates in output/)")
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
    # since=now truncates the log at the last "=== Daily run started" marker so
    # drop counts reflect tonight's run, not the whole log history.
    polish_stats = parse_polish_log(polish_log, since=datetime.now())
    runtime = pipeline_runtime_min(polish_log)

    monday = date.today() - timedelta(days=date.today().weekday())
    improvements = summarize_week_improvements(monday)

    common = dict(
        workbook_path=wb_path,
        workbook_rows=workbook_rows,
        week_n=week_n,
        today_csv_rows=today_rows,
        yesterday_csv_rows=yesterday_rows,
        heir_transfer_rows=heir_rows,
        polish_stats=polish_stats,
        runtime_min=runtime,
        include_heir_transfer=args.include_heir_transfer,
        improvements=improvements,
    )
    # Full report → attached .txt (every fine-print section, uncapped lists);
    # condensed report → the email body itself (most important items only).
    report = render_report(**common)
    email_body = render_report(**common, condensed=True)

    out_path = OUTPUT / f"daily_report_{date.today().strftime('%Y-%m-%d')}.txt"
    out_path.write_text(report, encoding="utf-8")
    email_path = OUTPUT / f"daily_report_{date.today().strftime('%Y-%m-%d')}_email.txt"
    email_path.write_text(email_body, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Wrote {email_path}")
    print()
    print(report)

    if args.no_email:
        return 0

    attachments = [out_path]
    if heir_path and args.include_heir_transfer:
        attachments.append(heir_path)
    if args.attach_workbook:
        attachments.append(wb_path)

    new_count = _count_new_cases(today_rows, yesterday_rows)
    subject = (f"NC Probate Wk {week_n} — {new_count} new today, "
               f"{len(today_rows)} this week")

    # Build the HTML email from the same report text + this-week stats.
    _eyeball = len(eyeball_cases(today_rows))
    _ready = sum(1 for r in today_rows
                 if _has_named_contact(r) and (r.get("Property Address") or "").strip())
    _counties = Counter((r.get("County") or "").strip() for r in today_rows).most_common()
    html = render_html_email(
        email_body, this_week=len(today_rows), new_count=new_count,
        ready=_ready, eyeball_n=_eyeball, counties=_counties, week_n=week_n,
    )

    ok, msg = send_email(subject, email_body, attachments=attachments, html=html)
    print(f"\nEmail: {msg}")
    return 0 if ok else 0  # File was written; email is best-effort


if __name__ == "__main__":
    sys.exit(main())
