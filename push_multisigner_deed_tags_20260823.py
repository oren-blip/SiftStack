"""Tag the estates whose DEED puts more than one person on title.

    python push_multisigner_deed_tags_20260823.py            # dry run
    python push_multisigner_deed_tags_20260823.py --apply

Source: output/heir_transfer_review_20260823.csv (heir_transfer_review_20260823.py).

Why: Step 4.96 already writes a `Multi-Signer (N)` flag, but it is built from the
court Beneficiaries column and stays in the workbook — the upload rebuilds Tags
per week, so it never reaches the CRM. The deed is both a stronger source (it
records who holds title, not who was named a beneficiary) and the one the caller
never sees. On 2026-08-23 all 15 in-CRM heir-transfer records with 2+ people on
title carried no multi-signer marking at all, so a caller could take a yes from
one owner that cannot convey the property.

Tag naming follows the existing `Multi-Signer (N)` convention where the deed
names an exact set of parties. Where the deed reads only "ETAL" the count is
genuinely unknown — "and others" — so those get `Multi-Signer (ETAL)` rather
than a fabricated number. Nothing else on the record is touched: no rename, no
mailing change, no status change.
"""
from __future__ import annotations
import argparse
import csv
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
SRC = REPO / "output" / "heir_transfer_review_20260823.csv"
OUT = REPO / "output" / "multisigner_deed_tags_20260823.csv"

VERIFY_TRIES, VERIFY_WAIT = 4, 3


def headers(tok: str) -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/",
            "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {tok}", "content-type": "application/json"}


def tag_for(row: dict) -> str:
    """Exact count when the deed lists the parties, ETAL when it does not."""
    signers = [s for s in (row.get("all_signers") or "").split("|") if s.strip()]
    raw = (row.get("deed_owner_raw") or "").upper()
    if len(signers) >= 2:
        return f"Multi-Signer ({len(signers)})"
    if "ETAL" in raw or "ET AL" in raw:
        return "Multi-Signer (ETAL)"
    return ""


def _call(method: str, url: str, **kw):
    """One request, surviving the transient TLS resets this host throws.

    apiv2 dropped the connection mid-handshake twice on 2026-08-23
    (ConnectionResetError 10054) while the network was otherwise healthy. An
    unguarded run dies on the first one and leaves the batch half-applied.
    """
    for attempt in range(4):
        try:
            return requests.request(method, url, timeout=30, **kw)
        except requests.exceptions.RequestException as e:
            if attempt == 3:
                raise
            print(f"      {type(e).__name__} - retrying in {2 ** attempt}s")
            time.sleep(2 ** attempt)


def read_tags(h: dict, uuid: str) -> set[str] | None:
    r = _call("GET", f"{API}/api/internal/property/{uuid}/", headers=h)
    if r.status_code != 200:
        return None
    d = r.json()
    d = d.get("data") or d
    return {(t.get("title") if isinstance(t, dict) else str(t)) or ""
            for t in (d.get("tags") or [])}


def add_tags(h: dict, uuid: str, titles: list[str]) -> bool:
    r = _call("POST", f"{API}/api/internal/property/{uuid}/add-tags/",
              headers=h, json={"tags": titles})
    return r.status_code in (200, 201, 202, 204)


def verify(h: dict, uuid: str, titles: list[str]) -> bool:
    """The write is durable before the read reflects it — retry before believing
    a failure (see project_datasift_search_index_stale)."""
    for attempt in range(VERIFY_TRIES):
        have = read_tags(h, uuid)
        if have is not None and all(t in have for t in titles):
            return True
        if attempt < VERIFY_TRIES - 1:
            time.sleep(VERIFY_WAIT)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the tags")
    args = ap.parse_args()

    rows = [r for r in csv.DictReader(SRC.open(encoding="utf-8-sig"))
            if r.get("uuid") and r.get("multi_signer")]
    print(f"{len(rows)} in-CRM heir transfers with 2+ people on title\n")

    h = headers(token())
    out = []
    for r in rows:
        tag = tag_for(r)
        case, uuid = r["case"], r["uuid"]
        if not tag:
            # Title held by one individual plus a TRUST. Both must convey, but
            # that is a trustee-authority question, not a headcount — flagging it
            # "Multi-Signer (2)" would tell the caller the wrong thing. Left for
            # a deliberate decision rather than folded in here.
            why = ("SKIP person + trust on title" if r.get("trust")
                   else "SKIP no readable party count")
            print(f"  {why:30s}{case} | {r['deed_owner_raw'][:52]}")
            out.append({**r, "tag": "", "result": why})
            continue

        have = read_tags(h, uuid)
        if have is None:
            print(f"  READ FAILED                   {case}")
            out.append({**r, "tag": tag, "result": "READ FAILED"})
            continue
        if any(t.startswith("Multi-Signer") for t in have):
            print(f"  SKIP already multi-signer     {case}")
            out.append({**r, "tag": tag, "result": "SKIP already tagged"})
            continue

        if not args.apply:
            print(f"  would tag {tag:22s} {case} | {r['crm_owner']:22s} | {r['deed_owner_raw'][:44]}")
            out.append({**r, "tag": tag, "result": "DRY RUN"})
            continue

        ok = add_tags(h, uuid, [tag]) and verify(h, uuid, [tag])
        state = "TAGGED (verified)" if ok else "FAILED"
        print(f"  {state:22s} {tag:22s} {case}")
        out.append({**r, "tag": tag, "result": state})

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        cols = ["case", "county", "crm_owner", "deed_owner_raw", "all_signers",
                "tag", "result", "uuid"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print("\n " + "  ".join(f"{n} {s}" for s, n in
                            Counter(o["result"] for o in out).most_common()))
    print(f"wrote {OUT}")
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
