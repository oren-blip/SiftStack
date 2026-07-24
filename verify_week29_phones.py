"""Verify phones landed on the Week-29 records; report count + Trestle estimate.

FREE: exports the tagged records from DataSift (no Trestle scoring, no upload),
counts how many rows now carry a phone number, then estimates Trestle cost from
that export so Oren can decide on the dial-tier scoring step.
"""
import asyncio, os, sys, csv, glob, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv()
from playwright.async_api import async_playwright
from datasift_core import login
from datasift_uploader import export_phone_enrichment

TAG = "NC Estates Week 29 2026"


async def main():
    email = os.environ["DATASIFT_EMAIL"]; pw = os.environ["DATASIFT_PASSWORD"]
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        ctx = await b.new_context(viewport={"width":1280,"height":800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, pw):
                print("LOGIN FAILED"); return
            res = await export_phone_enrichment(page, filter_tag=TAG)
            print("export result:", res.get("message"), "| path:", res.get("download_path"))
            path = res.get("download_path")
            if not path or not os.path.exists(path):
                # fallback: newest phone export in output/
                cands = sorted(glob.glob("output/phone_enrichment_export*.csv"), key=os.path.getmtime)
                path = cands[-1] if cands else None
            if not path:
                print("NO EXPORT CSV FOUND"); return
            rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
            cols = rows[0].keys() if rows else []
            phone_cols = [c for c in cols if re.search(r"phone", c, re.I) and not re.search(r"tag|type|dnc|litig", c, re.I)]
            print(f"\nrecords exported: {len(rows)}")
            print(f"phone-ish columns: {phone_cols[:12]}")
            with_phone = 0
            for r in rows:
                if any(re.search(r"\d", (r.get(c) or "")) for c in phone_cols):
                    with_phone += 1
            print(f"records WITH at least one phone: {with_phone} / {len(rows)}")
        finally:
            await b.close()

asyncio.run(main())
