"""Attach the per-record DP research packs to their DataSift "Property Files".

Supersedes the Playwright flow in attach_dp_reports.py. That script's premise --
"DataSift exposes no file API, every candidate endpoint 404s" -- was wrong by one
letter: the collection is /property/{uuid}/document/ (singular). The 2026-08-07
probe only tried "documents". Driving the browser cost ~20s per record; the API
does it in about one, and it needs no record search at all because the uuid comes
straight from the pack manifest, so the address-search misses that plagued the
UI run cannot happen.

The real upload is three calls, captured off the web app on 2026-08-22:
  1. GET  /api/internal/property/{uuid}/document/presigned-url/
         -> {"presigned_post": {"url": <s3>, "fields": {...}}}
  2. POST the file to that S3 url as multipart, fields first, "file" LAST
         (S3 ignores form fields that appear after the file part)  -> 204
  3. POST /api/internal/property/{uuid}/document/ with
         {size, storage_key, filename, extension}                  -> 201
     "filename" is the STEM; the extension is a separate field.

Idempotent: a record whose document list already holds the pack filename is
skipped, so a re-run after a partial failure costs nothing and never duplicates.

Usage:
    python attach_dp_packs_20260822.py --dry-run   # show the plan, upload nothing
    python attach_dp_packs_20260822.py --limit 3   # prove it on three records
    python attach_dp_packs_20260822.py            # attach everything outstanding
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from build_dp_packs_20260822 import documents, headers, token  # noqa: E402

API = "https://apiv2.reisift.io"
MANIFEST = REPO / "output" / "dp_pack_manifest_20260822.json"
RESULTS = REPO / "output" / "dp_pack_attach_results_20260822.csv"


def presign(h: dict, uuid: str) -> dict | None:
    r = requests.get(f"{API}/api/internal/property/{uuid}/document/presigned-url/",
                     headers=h, timeout=30)
    if r.status_code != 200:
        return None
    return (r.json() or {}).get("presigned_post")


def attach(h: dict, uuid: str, pdf: Path) -> tuple[bool, str]:
    post = presign(h, uuid)
    if not post or not post.get("url") or not post.get("fields"):
        return False, "presign failed"
    fields = post["fields"]
    data = [(k, (None, str(v))) for k, v in fields.items()]
    blob = pdf.read_bytes()
    # the file part MUST come last -- S3 discards any field it sees after it
    data.append(("file", (pdf.name, blob, "application/pdf")))
    r = requests.post(post["url"], files=data, timeout=120)
    if r.status_code not in (200, 201, 204):
        return False, f"S3 {r.status_code}: {r.text[:160]}"

    reg = requests.post(f"{API}/api/internal/property/{uuid}/document/", headers=h,
                        json={"size": len(blob), "storage_key": fields["key"],
                              "filename": pdf.stem, "extension": "pdf"}, timeout=60)
    if reg.status_code not in (200, 201):
        return False, f"register {reg.status_code}: {reg.text[:160]}"
    return True, "attached"


def run(dry: bool, limit: int | None) -> int:
    jobs = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"manifest: {len(jobs)} pack(s)")
    tok = token()
    if not tok:
        print("DataSift login failed")
        return 1
    h = headers(tok)

    todo, done_already, gone = [], 0, []
    for j in jobs:
        pdf = Path(j["pdf"])
        if not pdf.is_absolute():
            pdf = REPO / pdf
        if not pdf.exists():
            gone.append(j["stem"])
            continue
        docs = documents(h, j["uuid"])
        if docs is None:
            print(f"  ! lookup failed, will retry later: {j['stem']}")
            continue
        if any((d.get("filename") or "") == pdf.stem for d in docs):
            done_already += 1
            continue
        todo.append({**j, "path": pdf})

    print(f"already attached: {done_already}   to attach now: {len(todo)}"
          + (f"   MISSING PDF: {len(gone)}" if gone else ""))
    if limit:
        todo = todo[:limit]
        print(f"--limit {limit}: attaching {len(todo)}")
    if dry:
        for j in todo[:20]:
            print(f"   {j['stem']:52} -> {j['street'][:30]}")
        print("dry run - nothing uploaded")
        return 0

    ok, fail, rows = 0, 0, []
    for i, j in enumerate(todo, 1):
        good, msg = attach(h, j["uuid"], j["path"])
        rows.append({"stem": j["stem"], "uuid": j["uuid"], "street": j["street"],
                     "case": j.get("case", ""), "result": msg})
        if good:
            ok += 1
        else:
            fail += 1
            print(f"  FAIL {j['stem']}: {msg}")
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}  ok={ok} fail={fail}")

    with RESULTS.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stem", "uuid", "street", "case", "result"])
        w.writeheader()
        w.writerows(rows)
    print(f"\ndone {_dt.datetime.now():%Y-%m-%d %H:%M}: {ok} attached, {fail} failed")
    print(f"results: {RESULTS}")
    return 0 if fail == 0 else 2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    raise SystemExit(run(a.dry_run, a.limit))


if __name__ == "__main__":
    main()
