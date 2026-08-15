"""Cross-run disk cache for eCourts Parties fetches.

Why: the Parties endpoint is IP-throttled (~6 quick calls, then one per
~50s — see project_parties_api_throttle_heirs_of). The nightly polish
re-asks the court about the same unresolved cases every night, and the
midday top-up job (nc_parties_topup.py) exists purely to pre-fetch those
answers while the throttle window is otherwise idle. This cache is the
bridge between the two: the noon job writes, the 5 PM polish reads, and
every hit saves a ~55s throttle slot.

Rules:
- Only NON-EMPTY party lists are cached. An empty result is either the
  throttle lying or filing-day lag — both must be retried, never cached.
- Entries expire after NC_PARTIES_CACHE_TTL_HOURS (default 18): long
  enough to carry noon -> evening polish, short enough that late-added
  parties (beneficiaries land days after filing) are re-fetched daily.
- Corrupt/missing cache files are treated as empty, never fatal.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from ecourts_case_api import CaseAddress, CaseParty

CACHE_PATH = Path("output") / ".nc_parties_cache.json"
_TTL_SECONDS = float(os.environ.get("NC_PARTIES_CACHE_TTL_HOURS", "18") or 18) * 3600

_cache: dict | None = None
_hits = 0


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — missing/corrupt = empty
            _cache = {}
    return _cache


def _save() -> None:
    if _cache is None:
        return
    try:
        CACHE_PATH.parent.mkdir(exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_cache), encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception:  # noqa: BLE001 — cache write failure must never kill a run
        pass


def cache_get(case_hex: str) -> list[CaseParty] | None:
    """Fresh cached parties for a case, or None on miss/expiry."""
    global _hits
    if not case_hex:
        return None
    entry = _load().get(case_hex)
    if not entry:
        return None
    if time.time() - float(entry.get("at") or 0) > _TTL_SECONDS:
        return None
    try:
        parties = [
            CaseParty(
                **{**p, "addresses": [CaseAddress(**a) for a in p.get("addresses") or []]}
            )
            for p in entry.get("parties") or []
        ]
    except Exception:  # noqa: BLE001 — schema drift = treat as miss
        return None
    if not parties:
        return None
    _hits += 1
    return parties


def cache_put(case_hex: str, parties: list[CaseParty]) -> None:
    """Store a successful non-empty fetch. Empty lists are refused."""
    if not case_hex or not parties:
        return
    _load()[case_hex] = {"at": time.time(), "parties": [asdict(p) for p in parties]}
    _save()


def hits_this_process() -> int:
    return _hits


def prune() -> int:
    """Drop expired entries; returns how many were removed."""
    c = _load()
    now = time.time()
    stale = [k for k, v in c.items() if now - float((v or {}).get("at") or 0) > _TTL_SECONDS]
    for k in stale:
        del c[k]
    if stale:
        _save()
    return len(stale)
