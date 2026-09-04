import os, sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

def token():
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t: return t
    try:
        from get_ds_token import get_token
        t = get_token()
        if t: return t
    except Exception:
        pass
    from playwright.async_api import async_playwright
    from datasift_uploader import login
    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            pg = await (await b.new_context()).new_page()
            ok = await login(pg, os.environ.get("DATASIFT_EMAIL",""), os.environ.get("DATASIFT_PASSWORD",""))
            tk = await pg.evaluate("() => localStorage.getItem('rs_token')") if ok else None
            await b.close(); return tk
    return asyncio.run(go())
