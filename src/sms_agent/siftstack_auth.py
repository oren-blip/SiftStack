"""SiftStack's DataSift credential, for accounts without an Open API key.

Ty's `crm_standalone` authenticates with `authorization: Api-Key <key>` — the
no-expiry Open API key from the closed beta. This account is not in that beta,
so the agent would have no CRM at all on the standalone path.

It does not need one. Every endpoint `crm_standalone` touches lives under
`apiv2.reisift.io/api/internal/`, which is exactly what `trestle_api_backfill`
and `text_touch_api_backfill` already call nightly. Only the header differs:
`Bearer <rs_token>` instead of `Api-Key <key>`.

The cost of the swap is that a JWT expires and an Open API key does not. Ty
chose Api-Key precisely so a cloud worker could not die at 2am on a stale
token. So this module owns refresh: `token()` is cache-first and cheap, and
`refresh()` forces a new browser login. `crm_standalone` calls `refresh()` once
on a 401 and retries, which turns the expiry from an outage into a pause.

Resolution order, cheapest first:
  1. DS_TOKEN / DATASIFT_TOKEN in the environment (a pasted token, for tests)
  2. output/.ds_token.json, validated with one cheap GET before it is trusted
  3. Playwright login, which writes the cache for everyone else

Deliberately does NOT import trestle_api_backfill or text_touch_api_backfill.
Those pull in phone_validator and the whole enrichment stack; this has to stay
importable on a small box that carries none of it.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN_CACHE = ROOT / "output" / ".ds_token.json"
API = "https://apiv2.reisift.io"

# The cheapest authenticated GET on the account. Used only to decide whether a
# cached token is still alive, so it must not depend on any record existing.
_PROBE = "/api/internal/custom-fields/?entity_type=property"

_cached: Optional[str] = None


def headers(tok: str) -> dict:
    """Identical to trestle_api_backfill.headers, so the two agree by construction."""
    return {
        "authorization": f"Bearer {tok}",
        "content-type": "application/json",
        "accept": "application/json",
        "origin": "https://app.reisift.io",
        "referer": "https://app.reisift.io/",
        "user-agent": "Mozilla/5.0",
        "x-reisift-ui-version": "2022.02.01.7",
    }


def token_works(tok: str) -> bool:
    if not tok:
        return False
    try:
        r = requests.get(API + _PROBE, headers=headers(tok), timeout=20)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _from_env() -> str:
    for name in ("DS_TOKEN", "DATASIFT_TOKEN"):
        val = (os.environ.get(name) or "").strip().strip('"')
        if val:
            return val
    return ""


def _from_cache() -> str:
    try:
        return str(json.loads(TOKEN_CACHE.read_text(encoding="utf-8")).get("token", "")).strip()
    except (OSError, ValueError, AttributeError):
        return ""


def _write_cache(tok: str) -> None:
    try:
        TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE.write_text(json.dumps({"token": tok}), encoding="utf-8")
    except OSError as exc:
        log.warning("could not cache the DataSift token: %s", exc)


def _browser_login() -> str:
    """Playwright login for a fresh rs_token. The flaky part, hence last."""
    import asyncio
    import sys

    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    try:
        from playwright.async_api import async_playwright
        from datasift_uploader import login  # type: ignore
    except ImportError as exc:
        log.warning("browser login unavailable: %s", exc)
        return ""

    async def go() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await (await browser.new_context()).new_page()
                ok = await login(
                    page,
                    os.environ.get("DATASIFT_EMAIL", ""),
                    os.environ.get("DATASIFT_PASSWORD", ""),
                )
                if not ok:
                    return ""
                return (await page.evaluate("() => localStorage.getItem('rs_token')")) or ""
            finally:
                await browser.close()

    try:
        return (asyncio.run(go()) or "").strip()
    except Exception as exc:  # noqa: BLE001 - any login failure degrades the same way
        log.warning("DataSift browser login failed: %s", exc)
        return ""


def token(*, validate: bool = True) -> str:
    """A usable Bearer token, or "" when none can be obtained.

    `validate=False` skips the probe GET, for callers that will discover a dead
    token on their own next request anyway (the 401 path in crm_standalone).
    """
    global _cached
    if _cached and (not validate or token_works(_cached)):
        return _cached

    env = _from_env()
    if env:
        _cached = env
        return env

    cached = _from_cache()
    if cached and (not validate or token_works(cached)):
        _cached = cached
        return cached

    fresh = _browser_login()
    if fresh:
        _write_cache(fresh)
        _cached = fresh
        return fresh

    _cached = None
    return ""


def refresh() -> str:
    """Force a new token, ignoring env and cache. Called on a 401."""
    global _cached
    _cached = None
    fresh = _browser_login()
    if fresh:
        _write_cache(fresh)
        _cached = fresh
    return fresh or ""
