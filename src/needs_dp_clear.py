"""Retire the "Needs DP" marker once a record has a REAL contact.

The tag means one thing: "this record's contact is the placeholder
'Heirs of <Decedent>', so nobody has been identified yet." The moment a real
person lands on the record -- a court-named PR pushed by ``pr_upgrade_step``,
or a deep-prospecting result -- the marker is finished work and should come
off, and its "Needs DP - deep prospecting queued" task should close.

Nothing did that until 2026-09-09. Renames landed, the tag stayed, and the task
queue filled with overdue reminders for records that were already contactable
(39 tagged, 33 open tasks, 32 overdue, 11 of them already owned by a real
person). Oren's decision that day: keep the marker purely as a to-do list, and
make it clear itself.

DELIBERATELY NOT a marketing gate. No filter preset references this tag
(verified against all 25 presets on 2026-09-09), so removing it never moves a
record between calling lanes -- it only shortens the research queue.

Guards, learned the hard way elsewhere in this repo:
  * re-GET the record first and re-check the owner; never clear on the caller's
    say-so alone (a rename can silently fail -- see pr_upgrade_step's
    "SAVE DID NOT STICK" path and [[project_pr_upgrade_silent_save_failure]])
  * an owner still reading "Heirs"/"Estate" KEEPS the tag, always
  * verify the removal with another GET -- HTTP 200 is not proof
    ([[project_datasift_search_index_stale]]: never verify via search)
  * every failure is non-fatal and returns a reason string; this is cleanup,
    and it must never take down a nightly push
"""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

API = "https://apiv2.reisift.io"
NEEDS_DP_TAG = "Needs DP"
# The task title written by upload_netnew_datasift._create_needs_dp_tasks.
# Matched on this prefix so the em-dash tail can change without orphaning tasks.
TASK_PREFIX = "Needs DP"
_PLACEHOLDER_PREFIXES = ("heirs", "estate")


def _titles(items: Any) -> list[str]:
    return [t.get("title") if isinstance(t, dict) else str(t)
            for t in (items or [])]


def owner_name(rec: dict) -> str:
    o = rec.get("owner") or {}
    return " ".join(filter(None, [(o.get("first_name") or "").strip(),
                                  (o.get("last_name") or "").strip()])).strip()


def is_placeholder(name: str) -> bool:
    """True for the 'Heirs Smith' / 'Estate Of Smith' contacts we never call."""
    return (name or "").strip().lower().startswith(_PLACEHOLDER_PREFIXES)


def get_property(h: dict, uuid: str) -> dict | None:
    try:
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    d = r.json()
    return d.get("data", d)


def open_tasks(h: dict, uuid: str) -> list[dict]:
    """The record's un-completed Needs DP tasks."""
    try:
        r = requests.get(f"{API}/api/internal/task/", headers=h, timeout=30,
                         params={"property": uuid, "limit": 50})
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []
    rows = r.json().get("results") or r.json().get("data") or []
    return [t for t in rows
            if (t.get("title") or "").startswith(TASK_PREFIX) and not t.get("completed")]


def complete_task(h: dict, task: dict) -> bool:
    """Close one task, then re-read it to confirm.

    Two routes are tried because the dedicated one was only ever read out of
    the app bundle and had never been exercised against a live task until
    2026-09-09; the PATCH is the fallback if it is not really there.
    """
    tid = task.get("uuid")
    if not tid:
        return False
    for call in (
        lambda: requests.post(f"{API}/api/internal/task/{tid}/complete/",
                              headers=h, json={}, timeout=30),
        lambda: requests.patch(f"{API}/api/internal/task/{tid}/", headers=h,
                               json={"completed": True}, timeout=30),
    ):
        try:
            resp = call()
        except requests.RequestException:
            continue
        if resp.status_code not in (200, 201, 202, 204):
            continue
        try:
            chk = requests.get(f"{API}/api/internal/task/{tid}/", headers=h, timeout=30)
            if chk.status_code == 200:
                d = chk.json()
                if (d.get("data", d) or {}).get("completed"):
                    return True
            elif chk.status_code == 404:
                return True  # gone entirely counts as closed
        except requests.RequestException:
            pass
    return False


def clear(h: dict, uuid: str, *, dry_run: bool = False) -> tuple[bool, str]:
    """Take the Needs DP marker off one record and close its task.

    Returns (changed, reason). ``changed`` is False for every no-op, including
    the deliberate holds -- a record still owned by "Heirs X" keeps its tag.
    """
    rec = get_property(h, uuid)
    if rec is None:
        return False, "could not re-read the record"
    name = owner_name(rec)
    if not name:
        return False, "record has no owner name"
    if is_placeholder(name):
        return False, f"owner still reads {name!r} — tag is correct"
    tags = _titles(rec.get("tags"))
    tasks = open_tasks(h, uuid)
    if NEEDS_DP_TAG not in tags and not tasks:
        return False, "already clear"
    if dry_run:
        bits = []
        if NEEDS_DP_TAG in tags:
            bits.append("remove tag")
        if tasks:
            bits.append(f"close {len(tasks)} task(s)")
        return False, f"would {' + '.join(bits)} (owner {name!r})"

    removed = NEEDS_DP_TAG not in tags
    if not removed:
        try:
            requests.post(f"{API}/api/internal/property/{uuid}/remove-tags/",
                          headers=h, json={"tags": [NEEDS_DP_TAG]}, timeout=30)
        except requests.RequestException as e:  # noqa: BLE001
            return False, f"remove-tags call failed ({e})"
        after = get_property(h, uuid)
        if after is None:
            return False, "removal could not be verified (re-read failed)"
        removed = NEEDS_DP_TAG not in _titles(after.get("tags"))
        if not removed:
            return False, "VERIFY FAILED — tag still on the record after the write"

    closed = sum(1 for t in tasks if complete_task(h, t))
    note = f"tag removed (owner {name!r})"
    if tasks:
        note += f", {closed}/{len(tasks)} task(s) closed"
    return True, note


def clear_many(h: dict, uuids: list[str], *, dry_run: bool = False,
               label: str = "") -> int:
    """Best-effort sweep over several records. Logs one line each; never raises."""
    done = 0
    for u in uuids:
        try:
            changed, why = clear(h, u, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            logger.warning("Needs DP clear %s failed (%s)", u[:8], e)
            continue
        if changed:
            done += 1
            logger.info("Needs DP cleared %s%s: %s", label, u[:8], why)
        elif "still reads" not in why and "already clear" not in why:
            logger.warning("Needs DP not cleared %s%s: %s", label, u[:8], why)
    return done
