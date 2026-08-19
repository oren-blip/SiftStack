"""Fetch the written guides linked from a 5 Day Deal Flow Challenge day-hub page.

Each challenge day has a hub page (learn.datasift.ai/challenge-day-N) whose module
cards link to standalone guide pages by bare slug. This discovers those slugs and
saves each guide as clean markdown under knowledge/5-day-deal-flow/guides/day-N/.

    python scripts/fetch_challenge_guides.py 1
    python scripts/fetch_challenge_guides.py 2 --cohort-date 2026-08-18

Hub pages are sunset each cohort, so run this the same week the day airs.
Stdlib only.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE = "https://learn.datasift.ai"

# Nav/chrome slugs that appear on every hub page but are not guides.
NOT_GUIDES = re.compile(r"^(challenge-day-\d|challenge-hub)$")

BLOCK_END = re.compile(r"</(p|div|section|article|tr|table|ul|ol|blockquote)>", re.I)


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def to_markdown(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?is)<!--.*?-->", "", raw)
    raw = re.sub(r"(?is)<img[^>]*>", "", raw)
    for level in range(1, 5):
        raw = re.sub(
            rf"(?is)<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, l=level: "\n\n" + "#" * l + " " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "\n\n",
            raw,
        )
    raw = re.sub(r"(?is)<li[^>]*>", "\n- ", raw)
    raw = re.sub(r"(?is)<(strong|b)>(.*?)</\1>", r"**\2**", raw)
    raw = re.sub(r"(?is)<t[dh][^>]*>", " | ", raw)
    raw = BLOCK_END.sub("\n", raw)
    raw = re.sub(r"(?i)<br[^>]*>", "\n", raw)
    raw = re.sub(
        r'(?is)<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        lambda m: f"[{re.sub(r'<[^>]+>', '', m.group(2)).strip() or m.group(1)}]({m.group(1)})",
        raw,
    )
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    text = "\n".join(ln.rstrip() for ln in raw.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("day", type=int, help="challenge day number (1-5)")
    parser.add_argument("--cohort-date", default=None,
                        help="fetch date stamped into each file header (default: today)")
    args = parser.parse_args()

    stamp = args.cohort_date or time.strftime("%Y-%m-%d")
    out_dir = REPO_ROOT / "knowledge" / "5-day-deal-flow" / "guides" / f"day-{args.day}"
    out_dir.mkdir(parents=True, exist_ok=True)

    hub_url = f"{BASE}/challenge-day-{args.day}"
    hub = get(hub_url)
    slugs = sorted(
        {m.group(1) for m in re.finditer(r'href="([a-z0-9][a-z0-9-]*)"', hub)
         if not NOT_GUIDES.match(m.group(1))}
    )
    if not slugs:
        print(f"No guide slugs found on {hub_url} -- page layout may have changed.")
        return 1
    print(f"{len(slugs)} guides linked from {hub_url}")

    failed = 0
    for slug in slugs:
        url = f"{BASE}/{slug}"
        try:
            md = to_markdown(get(url))
        except Exception as exc:
            print(f"[fail] {slug}: {exc}")
            failed += 1
            continue
        header = (
            f"# Guide: {slug}\n\n"
            f"> Source: {url} (Day {args.day} module, fetched {stamp})\n"
            f"> Hub pages are sunset each cohort; this is the durable copy.\n\n"
            "---\n\n"
        )
        out = out_dir / f"{slug}.md"
        out.write_text(header + md + "\n", encoding="utf-8")
        print(f"[ok] {slug}: {len(md):,} chars")
        time.sleep(1)

    print(f"\nSaved to {out_dir.relative_to(REPO_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
