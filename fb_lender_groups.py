"""Survey Facebook for private-money-lender groups (READ ONLY - never clicks Join).

Step 1 of the private-money-lender harvest (Ty, 5DDF Day 5 [02:40:02]: search
"private money real estate" -> Groups tab, join them, then run the group scraper).

Two passes:
  mine    - every group Oren is already in (facebook.com/groups/joins/)
  search  - group-search results for the lender queries, with join state

Shares the one logged-in profile .fb_profile with fb_buyer_harvest.py, so only
one of them may run at a time (Chrome exit code 21 = someone else holds it).

    python fb_lender_groups.py            # both passes
    python fb_lender_groups.py --headless
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

import fb_buyer_harvest as fb

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "fb_lenders"
TODAY = datetime.now().strftime("%Y-%m-%d")

# Ty named the third one as the highest-traction group.
QUERIES = [
    "private money real estate",
    "private money lender",
    "real estate private money lenders",
    "private lenders real estate investing",
    "real estate funding investors",
]

# Groups worth surfacing out of "your groups" even though they are not lender groups.
MONEY_RE = re.compile(
    r"(private money|private lend|hard money|lender|lending|funding|fund(?:s|ing)? for|capital|"
    r"investor financ|money partner|jv partner|gap fund|note investor)", re.I)

GROUP_HREF_RE = re.compile(r"/groups/([^/?#]+)")

# Collect cards after EVERY scroll - the feed is virtualised and a single read at
# the end returns only the last screen (see fb-group-harvest-gotchas).
COLLECT_JS = """
() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\\/groups\\/([^\\/?#]+)/);
    if (!m) continue;
    const key = m[1];
    if (key === 'joins' || key === 'feed' || key === 'discover' || key === 'create') continue;
    let box = a;
    for (let i = 0; i < 8 && box.parentElement; i++) {
      box = box.parentElement;
      const t = (box.innerText || '');
      if (t.length > 40) break;
    }
    const text = (box.innerText || '').replace(/\\u034f|\\u200b|\\u200e/g, '').trim();
    const sig = key + '|' + text.slice(0, 80);
    if (seen.has(sig)) continue;
    seen.add(sig);
    out.push({key: key, name: (a.innerText || '').trim(), text: text.slice(0, 400)});
  }
  return out;
}
"""


def _digest(rows: list[dict]) -> dict[str, dict]:
    """Fold raw card reads into one record per group."""
    groups: dict[str, dict] = {}
    for row in rows:
        key = row["key"]
        rec = groups.setdefault(key, {"key": key, "name": "", "members": "", "privacy": "",
                                      "joined": None, "activity": "", "text": ""})
        name = row.get("name") or ""
        if name and len(name) > len(rec["name"]) and "member" not in name.lower():
            rec["name"] = name.split("\n")[0].strip()
        text = row.get("text") or ""
        if len(text) > len(rec["text"]):
            rec["text"] = text
    for rec in groups.values():
        t = rec["text"]
        if not rec["name"]:
            rec["name"] = t.split("\n")[0].strip()
        m = re.search(r"([0-9][0-9.,]*\s?[KM]?)\s+members", t, re.I)
        rec["members"] = m.group(1).strip() if m else "?"
        rec["privacy"] = ("Private" if re.search(r"\bPrivate group\b", t, re.I)
                          else "Public" if re.search(r"\bPublic group\b", t, re.I) else "?")
        m = re.search(r"(\d[\d.,]*\+?\s+posts? a (?:day|week|month))", t, re.I)
        rec["activity"] = m.group(1) if m else ""
        if re.search(r"^\s*(Joined|Visit)\s*$", t, re.I | re.M):
            rec["joined"] = True
        elif re.search(r"^\s*(Join group|Join)\s*$", t, re.I | re.M):
            rec["joined"] = False
        elif re.search(r"^\s*(Cancel request|Requested)\s*$", t, re.I | re.M):
            rec["joined"] = "requested"
    return groups


def _scroll_collect(page, rounds: int, label: str) -> list[dict]:
    rows: list[dict] = []
    for i in range(rounds):
        try:
            rows.extend(page.evaluate(COLLECT_JS))
        except Exception as exc:
            print(f"    read failed ({type(exc).__name__}) - continuing")
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(1400)
        if i % 4 == 3:
            print(f"    {label}: scroll {i + 1}/{rounds}, {len(_digest(rows))} groups so far", flush=True)
    rows.extend(page.evaluate(COLLECT_JS))
    return rows


def pass_mine(page) -> dict[str, dict]:
    print("\n=== groups you are already in ===", flush=True)
    page.goto("https://www.facebook.com/groups/joins/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    blocked = fb._blocked(page)
    if blocked:
        print(f"  Facebook says: {blocked}")
        return {}
    groups = _digest(_scroll_collect(page, 14, "your groups"))
    for rec in groups.values():
        rec["joined"] = True
        rec["source"] = "mine"
    print(f"  {len(groups)} groups found")
    return groups


def pass_search(page, queries: list[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for i, q in enumerate(queries, 1):
        print(f"\n=== search {i}/{len(queries)}: {q!r} ===", flush=True)
        url = "https://www.facebook.com/search/groups/?q=" + q.replace(" ", "%20")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        blocked = fb._blocked(page)
        if blocked:
            print(f"  Facebook says: {blocked} - stopping search pass")
            break
        rows = _scroll_collect(page, 10, q)
        got = _digest(rows)
        for key, rec in got.items():
            rec["source"] = "search"
            rec.setdefault("queries", [])
            prev = found.get(key)
            if prev:
                prev.setdefault("queries", []).append(q)
            else:
                rec["queries"] = [q]
                found[key] = rec
        print(f"  {len(got)} groups on this query ({len(found)} unique so far)")
        page.wait_for_timeout(2500)
    return found


def _members_num(rec: dict) -> float:
    m = re.match(r"([0-9.,]+)\s?([KM]?)", rec.get("members") or "")
    if not m:
        return -1.0
    n = float(m.group(1).replace(",", ""))
    return n * {"K": 1e3, "M": 1e6, "": 1}[m.group(2).upper()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--skip-mine", action="store_true")
    ap.add_argument("--queries", nargs="+")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx, page = fb._open(p, args.headless)
        mine = {} if args.skip_mine else pass_mine(page)
        found = pass_search(page, args.queries or QUERIES)
        ctx.close()

    for key, rec in found.items():
        if key in mine:
            rec["joined"] = True
    merged = {**{k: v for k, v in mine.items()}, **found}
    for key, rec in mine.items():
        if key in found:
            merged[key] = {**rec, **found[key], "joined": True}

    dest = OUT / f"lender_groups_{TODAY}.json"
    dest.write_text(json.dumps(merged, indent=1), encoding="utf-8")

    joined_money = [r for r in mine.values() if MONEY_RE.search(r["name"] + " " + r["text"])]
    candidates = sorted(
        [r for r in found.values() if r.get("joined") is not True],
        key=_members_num, reverse=True)
    already = sorted([r for r in found.values() if r.get("joined") is True],
                     key=_members_num, reverse=True)

    def show(rows, n=25):
        for r in rows[:n]:
            print(f"  {r['name'][:58]:<58} {r['members']:>7} {r['privacy']:<8} "
                  f"{r.get('activity', ''):<20} /groups/{r['key']}/")

    print("\n\n================ MONEY/LENDER GROUPS YOU ARE ALREADY IN ================")
    show(sorted(joined_money, key=_members_num, reverse=True)) if joined_money else print("  (none)")
    print("\n================ LENDER GROUPS IN SEARCH - ALREADY JOINED ================")
    show(already) if already else print("  (none)")
    print("\n================ LENDER GROUPS IN SEARCH - NOT JOINED ================")
    show(candidates) if candidates else print("  (none)")
    print(f"\nAll {len(merged)} groups -> {dest}")
    print(f"(you are in {sum(1 for r in merged.values() if r.get('joined') is True)} of them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
