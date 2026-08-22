"""Attach packs for estates that were deep-prospected but never TAGGED "DP Complete".

The main pass (build_dp_packs + attach_dp_packs) works the DP-Complete tag, so
it can only reach records that carry it. Nine sections of the 8/20 Heirs-of
sweep matched no tagged record at all -- their DataSift records exist, hold zero
documents, and are missing the tag. The research was done; only the bookkeeping
is missing, so the pack still belongs on the record.

Because there is no tag to anchor on, each case is resolved by searching the
account for the sweep's property address, keeping only a UNIQUE house-number
match, and then re-using the main pass's name gate: the record owner must appear
in that section as the decedent or the named decision-maker. Anything that fails
either test is reported for Oren rather than attached.

This does NOT add the missing tag -- tagging is a CRM write nobody asked for.
The unattached and untagged cases are printed so it can be decided separately.

Usage:
    python attach_dp_untagged_20260822.py --dry-run
    python attach_dp_untagged_20260822.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402

from attach_dp_packs_20260822 import attach  # noqa: E402
from build_dp_packs_20260822 import (  # noqa: E402
    HEIRS_MD, PACK_DIR, _addr_key, _owner_is_named_in, _safe, documents,
    dp_complete_records, headers, pack_markdown, parse_heading, split_sections,
    token,
)

API = "https://apiv2.reisift.io"
STATE = REPO / "output" / "dp_pack_state_20260822.json"
OUT = REPO / "output" / "dp_untagged_attach_20260822.json"


def search(h: dict, text: str) -> list[dict]:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": text}}, "limit": 200},
                      timeout=30)
    if r.status_code != 200:
        return []
    d = r.json()
    return d.get("results") or d.get("data") or []


def run(dry: bool) -> int:
    tok = token()
    if not tok:
        print("DataSift login failed")
        return 1
    h = headers(tok)

    want = {u["heading"] for u in json.loads(STATE.read_text())["unresolved"]}
    if not want:
        print("no unresolved sweep sections - nothing to do")
        return 0
    secs = [s for s in split_sections(HEIRS_MD) if s["heading"] in want]
    print(f"{len(secs)} sweep section(s) with no DP-Complete record\n")

    tagged = {r["uuid"] for r in dp_complete_records(h)}
    ready, skipped = [], []
    for sec in secs:
        meta = parse_heading(sec["heading"])
        label = f"{meta['name']} {meta['case']}"
        hits = search(h, meta["street"]) or search(h, meta["name"])
        key = _addr_key(meta["street"])
        exact = [x for x in hits
                 if _addr_key((x.get("address") or {}).get("street") or "") == key]
        if not exact:
            # A few sweep headings carry the city and state INSIDE the street
            # ("9112 TREE HAVEN DR CHARLOTTE NC, Charlotte"), so the record's
            # key is a prefix of the section's. Accept that only when it is
            # unique; the owner-name gate below still has to pass.
            exact = [x for x in hits
                     if (k := _addr_key((x.get("address") or {}).get("street") or ""))
                     and len(k) > 6 and key.startswith(k)]
        if len(exact) != 1:
            skipped.append({"case": meta["case"], "name": meta["name"],
                            "street": meta["street"], "city": meta["city"],
                            "why": f"{len(hits)} search hits, {len(exact)} address matches"})
            print(f"  SKIP  {label:34} {meta['street'][:28]:28} "
                  f"({len(hits)} hits, {len(exact)} address matches)")
            continue
        rec = exact[0]
        if not _owner_is_named_in(sec["body"], rec):
            o = rec.get("owner") or {}
            why = (f"owner {o.get('first_name', '')} {o.get('last_name', '')}".strip()
                   + " is not the decedent or DM in this section")
            skipped.append({"case": meta["case"], "name": meta["name"],
                            "street": meta["street"], "city": meta["city"], "why": why})
            print(f"  SKIP  {label:34} {why}")
            continue
        docs = documents(h, rec["uuid"])
        if docs is None:
            skipped.append({"case": meta["case"], "name": meta["name"],
                            "street": meta["street"], "why": "document lookup failed"})
            continue
        stem = f"DP_HeirsSweep_{_safe(meta['name'])}_{meta['case'] or _safe(meta['street'])[:14]}"
        if any((d.get("filename") or "") == stem for d in docs):
            print(f"  have  {label:34} already attached")
            continue
        ready.append({"uuid": rec["uuid"], "stem": stem, "meta": meta,
                      "body": sec["body"], "heading": sec["heading"],
                      "tagged": rec["uuid"] in tagged,
                      "record_street": (rec.get("address") or {}).get("street") or ""})
        print(f"  OK    {label:34} -> {(rec.get('address') or {}).get('street', '')[:30]:30} "
              f"tag={'yes' if rec['uuid'] in tagged else 'MISSING'}")

    print(f"\nattachable: {len(ready)}   needs a human: {len(skipped)}")
    OUT.write_text(json.dumps(
        {"ready": [{k: v for k, v in r.items() if k != "body"} for r in ready],
         "skipped": skipped}, indent=1), encoding="utf-8")
    if dry or not ready:
        print(f"dry run - nothing uploaded. detail: {OUT}" if dry else "")
        return 0

    PACK_DIR.mkdir(parents=True, exist_ok=True)
    from deep_prospect_pdf import render
    ok = fail = 0
    for j in ready:
        md = PACK_DIR / f"{j['stem']}.md"
        md.write_text(pack_markdown("Heirs-of backlog sweep, 2026-08-20", j["meta"],
                                    j["heading"], j["body"]), encoding="utf-8")
        pdf = Path(render(str(md)))
        good, msg = attach(h, j["uuid"], pdf)
        if good:
            ok += 1
        else:
            fail += 1
            print(f"  FAIL {j['stem']}: {msg}")
    print(f"\ndone: {ok} attached, {fail} failed")

    untagged = [j for j in ready if not j["tagged"]]
    if untagged:
        print(f"\nNOTE: {len(untagged)} of these records do NOT carry the "
              f'"DP Complete" tag despite the research being done:')
        for j in untagged:
            print(f"   {j['meta']['case']:16} {j['meta']['name'][:18]:18} "
                  f"{j['record_street'][:30]}")
    return 0 if fail == 0 else 2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    raise SystemExit(run(ap.parse_args().dry_run))


if __name__ == "__main__":
    main()
