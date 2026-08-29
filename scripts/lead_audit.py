"""Who is actually a lead right now, and how many of them are in the NSM flow.

The daily email's PHONES THIS WEEK line counts leads as *events* — records
whose status was moved into a lead status during the week. This script answers
the other two questions that line can't:

  1. What lead statuses does the account really use, and how many records sit
     in each one right now? (Also confirms whether the KPI puller's
     lead_statuses list matches the account's actual spelling — a mismatch is
     exactly what makes the email read "0 leads".)
  2. Of those lead records, how many are currently inside the niche sequential
     marketing (NSM) flow — i.e. matched by an NSM filter preset?

Read-only: nothing is written back to DataSift.

    python scripts/lead_audit.py                       # full audit
    python scripts/lead_audit.py --nsm-match "nsm|niche|sequential"
    python scripts/lead_audit.py --statuses-only       # just the status census

Token: the kpi-engine skill's reisift_token.txt (~48h), refreshed headlessly
with the same login the uploader uses, exactly like scripts/kpi_refresh.py.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

STATUS_ROUTES = ("property-status", "status", "propertystatus")


def get_token() -> str:
    """kpi_refresh's token path: saved token if alive, else headless login."""
    import kpi_refresh
    tok = (kpi_refresh.TOKEN_FILE.read_text(encoding="utf-8").strip()
           if kpi_refresh.TOKEN_FILE.exists() else "")
    if tok and kpi_refresh.token_alive(tok):
        return tok
    print("[audit] token dead — headless login for a fresh one", file=sys.stderr)
    tok = kpi_refresh.fresh_token_via_login()
    if not tok:
        sys.exit("DataSift login failed — check DATASIFT_EMAIL / DATASIFT_PASSWORD")
    kpi_refresh.TOKEN_FILE.write_text(tok, encoding="utf-8")
    return tok


def label_of(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("title") or obj.get("name") or obj.get("slug") or "")
    return str(obj or "")


def fetch_statuses(pk, token: str) -> list[dict]:
    """The account's property statuses. Route name has moved around; try all."""
    for route in STATUS_ROUTES:
        try:
            r = pk.req(token, f"/api/internal/{route}/", params={"limit": 200})
        except Exception:
            continue
        rows = r.get("results") or r.get("data") or (r if isinstance(r, list) else [])
        if isinstance(rows, list) and rows:
            return [x for x in rows if isinstance(x, dict)]
    return []


def query_records(pk, token: str, query: dict, cap: int = 20000) -> list[dict]:
    out, offset, limit = [], 0, 200
    while True:
        body = {"limit": limit, "offset": offset, "ordering": "-list_count", "query": query}
        r = pk.req(token, "/api/internal/property/", method="POST", body=body,
                   method_override="GET")
        rows = r.get("results") or r.get("data") or []
        out.extend(rows)
        total = r.get("count", len(out))
        offset += limit
        if offset >= total or not rows or offset >= cap:
            break
    return out


def lead_records(pk, token: str, lead_ids: list, bucket_all: bool) -> list[dict]:
    """Records currently in a lead status.

    Preferred path is the account's own status filter (cheap). If the API
    rejects it, or the ids don't come back as advertised, fall back to paging
    every clean record and bucketing by the status the record reports.
    """
    if lead_ids and not bucket_all:
        try:
            recs = query_records(pk, token, {"must": {"property_type": "clean",
                                                      "any_property_status": lead_ids}})
            if recs:
                return recs
            print("[audit] status filter returned 0 — falling back to a full scan",
                  file=sys.stderr)
        except Exception as e:
            print(f"[audit] status filter rejected ({e}) — full scan instead", file=sys.stderr)
    return query_records(pk, token, {"must": {"property_type": "clean"}})


def nsm_presets(pk, token: str, pattern: str) -> list[dict]:
    r = pk.req(token, "/api/internal/filter-preset/", params={"limit": 300})
    presets = r.get("results") or r.get("data") or []
    rx = re.compile(pattern, re.I)
    out = []
    for p in presets:
        if not isinstance(p, dict):
            continue
        name = label_of(p.get("title") or p.get("name"))
        folder = label_of(p.get("folder"))
        if rx.search(name) or rx.search(folder):
            out.append({"uuid": p.get("uuid") or p.get("id"), "name": name,
                        "folder": folder, "query": p.get("query") or p.get("filters")
                        or p.get("filter")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Lead census + NSM membership (read-only)")
    ap.add_argument("--nsm-match", default=r"nsm|niche|sequential",
                    help="regex matched against preset name AND folder (default: nsm|niche|sequential)")
    ap.add_argument("--statuses-only", action="store_true",
                    help="print the status census and stop")
    ap.add_argument("--full-scan", action="store_true",
                    help="skip the status filter and bucket every clean record client-side")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    from weekly_kpis import _load_pull_kpis
    pk = _load_pull_kpis(called_only=False)
    bench = pk.load_benchmarks()
    lead_set = {pk.norm_status(s) for s in bench["lead_statuses"]}
    token = get_token()

    statuses = fetch_statuses(pk, token)
    print("\n=== Property statuses defined in the account ===")
    if not statuses:
        print("  (status endpoint returned nothing — status labels below come "
              "from the records themselves)")
    lead_ids = []
    for st in statuses:
        name = label_of(st)
        matched = pk.norm_status(name) in lead_set
        if matched:
            lead_ids.append(st.get("uuid") or st.get("id") or st.get("slug"))
        print(f"  {'LEAD  ' if matched else '      '}{name}")
    unknown = [label_of(s) for s in statuses if pk.norm_status(label_of(s)) not in lead_set]
    if statuses and not lead_ids:
        print("\n  !! none of the account's statuses match the KPI lead list "
              f"({', '.join(bench['lead_statuses'])}).\n"
              "     That alone makes the daily email read 0 leads. Fix by adding the\n"
              "     real names to lead_statuses in "
              ".claude/skills/kpi-engine/scripts/benchmarks.json")
    if args.statuses_only:
        return 0

    recs = lead_records(pk, token, [i for i in lead_ids if i], args.full_scan)
    leads, by_status = [], {}
    for rec in recs:
        name = label_of(rec.get("status"))
        if pk.norm_status(name) not in lead_set:
            continue
        leads.append(rec)
        by_status[name] = by_status.get(name, 0) + 1
    print(f"\n=== Records currently in a lead status: {len(leads)} ===")
    for name, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  {name}")
    if unknown and not by_status:
        print(f"  (statuses seen on records instead: {', '.join(sorted(unknown)[:12])})")

    presets = nsm_presets(pk, token, args.nsm_match)
    print(f"\n=== NSM presets matching /{args.nsm_match}/: {len(presets)} ===")
    lead_uuids = {r.get("uuid") for r in leads}
    in_nsm: dict[str, set] = {}
    for p in presets:
        if not p["query"]:
            print(f"  {p['name']}: no stored query — skipped")
            continue
        try:
            matched = {r.get("uuid") for r in query_records(pk, token, p["query"])}
        except Exception as e:
            print(f"  {p['name']}: query failed ({e})")
            continue
        hits = matched & lead_uuids
        print(f"  [{p['folder']}] {p['name']}: {len(matched)} records, {len(hits)} of them leads")
        for u in hits:
            in_nsm.setdefault(u, set()).add(p["name"])

    print(f"\n=== {len(in_nsm)} of {len(leads)} lead records are in the NSM flow ===")
    if leads:
        out = ROOT / "output" / f"lead_audit_{datetime.date.today().isoformat()}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["uuid", "street", "city", "state", "zip", "owner", "status",
                        "in_nsm", "nsm_presets", "lists", "tags", "call_attempts",
                        "dm_attempts"])
            for rec in leads:
                a = rec.get("address") or {}
                ow = rec.get("owner") or {}
                u = rec.get("uuid")
                w.writerow([u, a.get("street"), a.get("city"), a.get("state"),
                            a.get("zip_code") or a.get("zip"),
                            f"{ow.get('first_name', '')} {ow.get('last_name', '')}".strip(),
                            label_of(rec.get("status")),
                            "YES" if u in in_nsm else "",
                            "|".join(sorted(in_nsm.get(u, ()))),
                            "|".join(label_of(x) for x in (rec.get("lists") or [])),
                            "|".join(label_of(x) for x in (rec.get("tags") or [])),
                            rec.get("predictivecall_attempts"),
                            rec.get("directmail_attempts")])
        print(f"[saved] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
