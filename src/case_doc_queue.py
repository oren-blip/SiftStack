"""Pending-document queue for cases whose attachments aren't yet uploaded.

Some Odyssey case docket entries appear immediately (e.g. "Last Will and
Testament filed") but the actual PDF takes hours or days to be processed
and uploaded by the clerk. Without retry tracking, a single missed fetch
means we never get that document.

This module owns two JSON files in ``output/``:

  - ``pending_case_docs.json``: cases awaiting one or more document types.
    Keyed by case_id_hex. Each entry tracks ``needs`` (doc types still
    missing), ``first_seen_iso``, ``last_attempt_iso``, ``retry_count``.

  - ``fetched_case_docs.json``: successfully fetched + parsed doc data.
    Keyed by case_id_hex. Each entry maps doc_type → structured dict.
    Polish reads this and applies to rows matched by case_id_hex.

Retry policy: a case stays in the queue until either every needed doc
has been fetched, or it ages past ``MAX_PENDING_DAYS`` (default 30) at
which point we give up — clerk almost certainly never uploaded.

Doc-type registry lives here so adding a new type (Application, Cover
Sheet) is a single ``register_doc_type`` call from extractor modules.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── State files ───────────────────────────────────────────────────────


_PENDING_PATH = Path("output") / "pending_case_docs.json"
_FETCHED_PATH = Path("output") / "fetched_case_docs.json"

MAX_PENDING_DAYS = int(os.environ.get("CASE_DOC_QUEUE_MAX_DAYS", "30"))
# High-priority cases (no-PR survivors) are kept longer — the court may scan the
# Application/Will months after filing, and the executor name matters most here.
PRIORITY_PENDING_DAYS = int(os.environ.get("CASE_DOC_QUEUE_PRIORITY_DAYS", "90"))

# Schema version — bump when the JSON shape changes so we know to re-derive.
_SCHEMA_VERSION = 1

_lock = threading.Lock()


# ── Doc-type registry ────────────────────────────────────────────────


@dataclass
class DocTypeSpec:
    """Description of one document type we know how to fetch + parse.

    - ``key``: short identifier used in queue entries and fetched store
      (e.g. ``"will"``, ``"application"``, ``"cover_sheet"``).
    - ``label_regex``: matches against event_label, event_type_desc, and
      document_name to identify this doc type in a case docket.
    - ``parser``: callable(text_str, *, api_key) -> dict. Returns the
      structured data we want to capture for this doc type. Empty dict
      means parse failed or not applicable; queue will keep retrying.
    """
    key: str
    label_regex: re.Pattern
    parser: Callable[..., dict[str, Any]]


_DOC_TYPES: dict[str, DocTypeSpec] = {}


def register_doc_type(spec: DocTypeSpec) -> None:
    """Register a document type the queue knows how to retry + parse."""
    _DOC_TYPES[spec.key] = spec


def known_doc_types() -> list[str]:
    return list(_DOC_TYPES.keys())


def get_doc_type(key: str) -> DocTypeSpec | None:
    return _DOC_TYPES.get(key)


def matches_doc_type(key: str, event_label: str, event_type_desc: str, document_name: str) -> bool:
    """Check if a docket entry matches a registered doc type."""
    spec = _DOC_TYPES.get(key)
    if not spec:
        return False
    for text in (event_label, event_type_desc, document_name):
        if text and spec.label_regex.search(text):
            return True
    return False


# ── Persistence layer ────────────────────────────────────────────────


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_version": _SCHEMA_VERSION, "entries": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read %s (%s) — starting fresh", path.name, e)
        return {"_version": _SCHEMA_VERSION, "entries": {}}
    if not isinstance(data, dict) or data.get("_version") != _SCHEMA_VERSION:
        logger.info("Schema mismatch in %s — starting fresh", path.name)
        return {"_version": _SCHEMA_VERSION, "entries": {}}
    return data


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(path)


def load_pending() -> dict[str, dict]:
    with _lock:
        return _load(_PENDING_PATH).get("entries", {})


def load_fetched() -> dict[str, dict]:
    with _lock:
        return _load(_FETCHED_PATH).get("entries", {})


def _save_pending(entries: dict[str, dict]) -> None:
    with _lock:
        _save(_PENDING_PATH, {"_version": _SCHEMA_VERSION, "entries": entries})


def _save_fetched(entries: dict[str, dict]) -> None:
    with _lock:
        _save(_FETCHED_PATH, {"_version": _SCHEMA_VERSION, "entries": entries})


# ── Queue API ────────────────────────────────────────────────────────


def get_fetched(case_id_hex: str, doc_type: str) -> dict | None:
    """Return previously fetched + parsed data for a case's doc type, or None."""
    entries = load_fetched()
    return (entries.get(case_id_hex) or {}).get(doc_type)


def record_fetched(case_id_hex: str, doc_type: str, parsed: dict) -> None:
    """Store successfully parsed doc data. Idempotent — overwrites prior."""
    if not parsed:
        return
    entries = load_fetched()
    case_entry = entries.setdefault(case_id_hex, {})
    case_entry[doc_type] = parsed
    _save_fetched(entries)


def add_to_pending(
    case_id_hex: str, *, case_number: str, county: str, notice_type: str,
    needed_doc_types: list[str],
) -> None:
    """Add a case to the pending queue. If already present, merges
    needed_doc_types and refreshes last_attempt_iso."""
    if not case_id_hex or not needed_doc_types:
        return
    now = datetime.now(timezone.utc).isoformat()
    entries = load_pending()
    existing = entries.get(case_id_hex)
    if existing:
        # Merge needed list (keep distinct)
        prior = set(existing.get("needs", []))
        existing["needs"] = sorted(prior | set(needed_doc_types))
        existing["last_attempt_iso"] = now
        existing["retry_count"] = int(existing.get("retry_count", 0)) + 1
    else:
        entries[case_id_hex] = {
            "case_number": case_number,
            "county": county,
            "notice_type": notice_type,
            "needs": sorted(set(needed_doc_types)),
            "first_seen_iso": now,
            "last_attempt_iso": now,
            "retry_count": 0,
        }
    _save_pending(entries)


def mark_fetched(case_id_hex: str, doc_type: str) -> None:
    """Remove a doc type from a case's pending needs. If no needs remain,
    remove the case from the queue."""
    entries = load_pending()
    existing = entries.get(case_id_hex)
    if not existing:
        return
    needs = [d for d in existing.get("needs", []) if d != doc_type]
    if needs:
        existing["needs"] = needs
        existing["last_attempt_iso"] = datetime.now(timezone.utc).isoformat()
    else:
        del entries[case_id_hex]
    _save_pending(entries)


def expire_old(max_days: int = MAX_PENDING_DAYS, *,
               keep_case_numbers: set[str] | None = None,
               keep_days: int = PRIORITY_PENDING_DAYS) -> int:
    """Drop queue entries older than max_days. Returns count expired.

    Courts scan the Application/Will into Odyssey on a lag (days to weeks, or
    never for paper-only filings), so we keep retrying — nightly — for a window
    rather than giving up after one miss. High-priority cases get a LONGER
    window: pass `keep_case_numbers` (the no-PR survivors from
    cases_needing_docs) and those are kept `keep_days` instead of `max_days`.
    The missing executor name matters most on exactly those, so it's worth
    chasing a late scan for months before writing the case off to a manual
    courthouse pull.
    """
    keep_case_numbers = {c.strip().upper() for c in (keep_case_numbers or set())}
    now = datetime.now(timezone.utc)
    entries = load_pending()
    expired_ids = []
    for cid, e in entries.items():
        try:
            first = datetime.fromisoformat(e.get("first_seen_iso", ""))
            if first.tzinfo is None:
                first = first.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        cn = (e.get("case_number") or "").strip().upper()
        limit = keep_days if cn in keep_case_numbers else max_days
        if first < now - timedelta(days=limit):
            expired_ids.append(cid)
    for cid in expired_ids:
        del entries[cid]
    if expired_ids:
        _save_pending(entries)
        logger.info("case_doc_queue: expired %d entries (%d-day default, %d-day priority)",
                    len(expired_ids), max_days, keep_days)
    return len(expired_ids)


def long_pending_high_priority(keep_case_numbers: set[str],
                               min_age_days: int = 21) -> list[dict]:
    """High-priority cases whose document the court still hasn't scanned after
    `min_age_days`. These are the manual-courthouse-pull candidates — we've
    retried nightly for weeks and the PDF never appeared. Returns entry dicts
    with an added `age_days`, oldest first.
    """
    keep = {c.strip().upper() for c in keep_case_numbers}
    now = datetime.now(timezone.utc)
    out = []
    for e in load_pending().values():
        cn = (e.get("case_number") or "").strip().upper()
        if cn not in keep:
            continue
        try:
            first = datetime.fromisoformat(e.get("first_seen_iso", ""))
            if first.tzinfo is None:
                first = first.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        age = (now - first).days
        if age >= min_age_days:
            out.append({**e, "age_days": age})
    out.sort(key=lambda e: e["age_days"], reverse=True)
    return out


def pending_summary() -> dict[str, Any]:
    """Counts for visibility in logs / dashboards."""
    entries = load_pending()
    by_doc_type: dict[str, int] = {}
    for e in entries.values():
        for d in e.get("needs", []):
            by_doc_type[d] = by_doc_type.get(d, 0) + 1
    return {
        "total_cases": len(entries),
        "by_doc_type": by_doc_type,
    }
