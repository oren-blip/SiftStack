"""Q5 2026-08-19: READ-ONLY discovery — find the NSM flow's step-10 preset
("No Response DM -> DP") in DataSift, dump its filter definition, and list
the records currently matching it. No writes.

Run:  d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_nsm10_discover_20260819.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"
OUT = REPO / "output" / "nsm10_discover_20260819"
OUT.mkdir(parents=True, exist_ok=True)


def headers(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}", "content-type": "application/json",
            "accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7"}


def get_token() -> str:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        return t
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            tok = (await page.evaluate("() => localStorage.getItem('rs_token')")
                   if ok else None)
            await b.close()
            return tok
    tok = asyncio.run(go())
    if not tok:
        raise RuntimeError("DataSift login failed")
    return tok


def main() -> int:
    h = headers(get_token())

    # 1. All filter presets
    r = requests.get(f"{API}/api/internal/filter-preset/", headers=h,
                     params={"limit": 200}, timeout=30)
    r.raise_for_status()
    presets = r.json().get("results") or r.json().get("data") or []
    (OUT / "presets_all.json").write_text(
        json.dumps(presets, indent=1), encoding="utf-8")
    print(f"{len(presets)} presets:")
    target = None
    for p in presets:
        name = p.get("title") or p.get("name") or ""
        folder = (p.get("folder") or {}).get("title") if isinstance(p.get("folder"), dict) else p.get("folder")
        print(f"  [{folder}] {name}")
        low = name.lower()
        if "no response" in low and ("dp" in low or "deep" in low or "10" in low):
            target = p
    if target is None:
        for p in presets:
            name = (p.get("title") or p.get("name") or "").lower()
            if name.strip().startswith("10"):
                target = p
                break
    if target is None:
        print("\nNO step-10 / No-Response preset found — see presets_all.json")
        return 1

    print(f"\nTARGET preset: {target.get('title') or target.get('name')}")
    uuid = target.get("uuid") or target.get("id")
    r = requests.get(f"{API}/api/internal/filter-preset/{uuid}/", headers=h, timeout=30)
    detail = r.json() if r.status_code == 200 else target
    (OUT / "preset_target.json").write_text(
        json.dumps(detail, indent=1), encoding="utf-8")
    print(json.dumps(detail, indent=1)[:3000])

    # 2. Records matching the preset's stored query
    query = detail.get("query") or detail.get("filters") or detail.get("filter")
    if not query:
        print("\npreset has no stored query field — inspect preset_target.json")
        return 1
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset, "query": query},
                          timeout=60)
        if r.status_code != 200:
            print(f"records query -> HTTP {r.status_code}: {r.text[:400]}")
            return 1
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    (OUT / "records.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n{len(out)} record(s) match the preset:")
    for rec in out:
        a = rec.get("address") or {}
        ow = rec.get("owner") or {}
        tags = [t.get("title") if isinstance(t, dict) else str(t)
                for t in (rec.get("tags") or [])]
        print(f"  {rec.get('uuid','')[:8]}  {a.get('street','?'):28} "
              f"{a.get('city','?'):15} owner={ow.get('first_name','')} {ow.get('last_name','')} "
              f"phones={len(ow.get('phones') or [])} tags={tags[:6]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
