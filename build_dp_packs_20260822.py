"""Split the bulk DP sweep reports into ONE research pack per DataSift record.

WHY: 232 records carry the "DP Complete" tag but only 33 have a file attached
(audited 2026-08-22 via GET /property/{uuid}/document/ -- an endpoint the 8/07
probe missed because it only tried the plural "documents"). Those 33 are the
per-case Week31-33 packs. The other 199 were worked in the two BULK sweeps --
NSM step-10 (8/19, 121 records) and the Heirs-of backlog (8/20, 87 sections) --
each written as ONE combined markdown. There was never a per-record artifact to
attach, which is the whole gap.

This splits those combined files back into per-record markdown, resolves each
section to its DataSift record uuid, and renders a PDF via src/deep_prospect_pdf.py.

Resolution differs per source, on purpose:
  * NSM10 sections embed the uuid ("DataSift record: <uuid>") -- exact, trusted.
  * HeirsSweep sections carry Case No. + property address only, so they are
    matched against the live DP-Complete record set by normalized street+city.
    An address matching more than one live record is left UNRESOLVED rather than
    guessed -- filing a research pack on the wrong estate is the one failure
    mode that actually costs something (cf. Baker 26E002844-590, whose parcel
    turned out to belong to a different Joseph Baker).

Usage:
    python build_dp_packs_20260822.py --audit    # what's missing, build nothing
    python build_dp_packs_20260822.py            # build packs + render PDFs
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"
DP_COMPLETE_TAG = "40b488ce-d7b8-4122-aff6-2fae0a58fea2"
REPORT_DIR = REPO / "output" / "reports"
PACK_DIR = REPORT_DIR / "packs"
STATE = REPO / "output" / "dp_pack_state_20260822.json"
MANIFEST = REPO / "output" / "dp_pack_manifest_20260822.json"

HEIRS_MD = REPORT_DIR / "DP_HeirsSweep_20260820.md"
NSM10_MD = REPORT_DIR / "DP_NSM10_NoResponse_20260819.md"

UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
CASE_RE = re.compile(r"(\d{2}E\d{6}-\d{3})")
# the sweep files were written with an em dash that got mangled to U+FFFD in
# places, so every plausible separator is accepted
DASH_RE = re.compile("\\s[\u2013\u2014\ufffd\\-]\\s")


# ---------------------------------------------------------------- auth / API
def token() -> str:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        return t
    import asyncio

    from playwright.async_api import async_playwright

    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            tk = (await page.evaluate("() => localStorage.getItem('rs_token')")
                  if ok else None)
            await b.close()
            return tk
    return asyncio.run(go()) or ""


def headers(tok: str) -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/",
            "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {tok}", "content-type": "application/json"}


def dp_complete_records(h: dict) -> list[dict]:
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset,
                                "query": {"must": {"any_tags": [DP_COMPLETE_TAG]}}},
                          timeout=60)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            return out
        offset += 200


def documents(h: dict, uuid: str) -> list[dict] | None:
    """Attached files, or None if the lookup itself failed (never treat an
    error as 'no files' -- that would re-upload duplicates)."""
    try:
        r = requests.get(f"{API}/api/internal/property/{uuid}/document/",
                         headers=h, timeout=25)
    except requests.RequestException:
        return None
    return (r.json().get("results") or []) if r.status_code == 200 else None


# ---------------------------------------------------------------- md parsing
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# The sweep headings and the DataSift records disagree on street spelling far
# more often than they disagree on the actual property: "4709 Wildwood Av" vs
# "4709 Wildwood Ave", "1026 10Th St Ct Nw" vs "1026 10th Street Ct NW". Every
# one of the 18 first-pass misses was cosmetic, so suffixes are folded to a
# canonical form before comparison instead of being matched literally.
_SUFFIX = {
    "av": "ave", "avenue": "ave", "aven": "ave",
    "st": "st", "street": "st", "str": "st",
    "rd": "rd", "road": "rd",
    "dr": "dr", "drive": "dr", "drv": "dr",
    "ln": "ln", "lane": "ln",
    "ct": "ct", "court": "ct",
    "pl": "pl", "place": "pl", "plc": "pl",
    "cir": "cir", "circle": "cir",
    "blvd": "blvd", "boulevard": "blvd",
    "hwy": "hwy", "highway": "hwy",
    "pkwy": "pkwy", "parkway": "pkwy",
    "trl": "trl", "trail": "trl", "tr": "trl",
    "ter": "ter", "terrace": "ter",
    "n": "n", "north": "n", "s": "s", "south": "s",
    "e": "e", "east": "e", "w": "w", "west": "w",
    "ne": "ne", "nw": "nw", "se": "se", "sw": "sw",
}
# ordinals: "10Th" / "10th" / "33Rd" all collapse to the bare number, and the
# spelled-out form too ("401 W First St" is "401 W 1St St" in DataSift)
_ORD_RE = re.compile(r"^(\d+)(st|nd|rd|th)$")
_ORD_WORD = {"first": "1", "second": "2", "third": "3", "fourth": "4",
             "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8",
             "ninth": "9", "tenth": "10", "eleventh": "11", "twelfth": "12"}
# "Unit 203", "Apt 4B", or a bare trailing "203" -- the record and the heading
# disagree about whether the unit is carried, so it is dropped from the key
_UNIT_RE = re.compile(r"\b(unit|apt|apartment|ste|suite|#)\b.*$", re.I)


def _addr_key(street: str) -> str:
    """Canonical street key: house number + folded, unit-stripped tokens."""
    s = _UNIT_RE.sub("", (street or "").lower())
    toks = []
    for t in re.findall(r"[a-z0-9]+", s):
        m = _ORD_RE.match(t)
        if m:
            t = m.group(1)
        t = _ORD_WORD.get(t, t)
        toks.append(_SUFFIX.get(t, t))
    # a bare trailing number that is not the house number is a unit -- drop it
    if len(toks) > 2 and toks[-1].isdigit() and not toks[-2].isdigit():
        toks = toks[:-1]
    return "".join(toks)


def split_sections(path: Path) -> list[dict]:
    """-> [{heading, body}] for every '## ' block, skipping the intro."""
    txt = path.read_text(encoding="utf-8", errors="replace")
    out = []
    for chunk in re.split(r"^## ", txt, flags=re.M)[1:]:
        head, _, body = chunk.partition("\n")
        out.append({"heading": head.strip(), "body": body.rstrip()})
    return out


def parse_heading(heading: str) -> dict:
    """'Vance 26E000432-540 - 2137 Brevard Place Rd, Iron Station (Lincoln)'."""
    m = CASE_RE.search(heading)
    case = m.group(1) if m else ""
    county = ""
    m = re.search(r"\(([^)]+)\)\s*$", heading)
    if m:
        county = m.group(1).strip()
    addr = ""
    parts = DASH_RE.split(heading, maxsplit=1)
    if len(parts) == 2:
        addr = re.sub(r"\s*\([^)]+\)\s*$", "", parts[1]).strip()
    street, _, city = addr.partition(",")
    name = (heading.split(case)[0] if case else parts[0]).strip()
    return {"case": case, "county": county, "street": street.strip(),
            "city": city.strip(), "name": name.strip()}


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", s or "") or "Record"


def _owner_is_named_in(body: str, rec: dict) -> bool:
    """Does this record's owner appear in the section as the decedent or the DM?

    A shared surname is NOT enough. Left on surname alone this tier proposed
    filing the MECKLENBURG Foster estate (26E001945-590, 4427 Hamilton Cr) onto
    the ROWAN record 2683 Oddie Rd / Martha Foster -- a different family, a
    different case. Requiring the record owner's first AND last name to appear
    as either the decedent or the named decision-maker keeps the two matches
    this tier exists for (Hines' second parcel, whose owner IS the decedent;
    Vance, whose owner was renamed to the DM) and rejects that one.
    """
    o = rec.get("owner") or {}
    # tokenise BOTH sides -- a first_name field routinely holds two words
    # ("Paul Ray"), which never matches a whole-string compare
    own = {_norm(t) for t in re.findall(r"[A-Za-z]+",
                                        f"{o.get('first_name') or ''} "
                                        f"{o.get('last_name') or ''}")}
    if len(own) < 2:
        return False
    names = []
    m = re.search(r"^-\s*Decedent:\s*([^|\n]+)", body, re.M)
    if m:
        names.append(m.group(1))
    m = re.search(r"^-\s*DM:\s*\*\*([^*]+)\*\*", body, re.M)
    if m:
        names.append(m.group(1))
    for n in names:
        toks = {_norm(t) for t in re.findall(r"[A-Za-z]+", n)}
        if own <= toks:
            return True
    return False


# ---------------------------------------------------------------- pack build
def pack_markdown(src_label: str, meta: dict, heading: str, body: str) -> str:
    """One self-contained research pack -- what a caller opens on a phone."""
    lines = [f"# Deep Prospecting Pack - {meta.get('name') or heading}", ""]
    bits = []
    if meta.get("case"):
        bits.append(f"**Case No.** {meta['case']}")
    if meta.get("street"):
        loc = meta["street"] + (f", {meta['city']}" if meta.get("city") else "")
        bits.append(f"**Property** {loc}")
    if meta.get("county"):
        bits.append(f"**County** {meta['county']}")
    bits.append(f"**Research run** {src_label}")
    lines += [" | ".join(bits), "", "---", "", "## Research findings", "",
              body.strip(), "", "---", "",
              "Dial tiers are Trestle activity scores: 81-100 Dial First, 61-80",
              "Dial Second, 41-60 Dial Third, 21-40 Dial Fourth, 0-20 Drop.",
              'Phones tagged "Litigator - DNC" are suppressed from all marketing.',
              ""]
    return "\n".join(lines)


def collect_jobs(missing: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """-> (jobs, unresolved heirs sections, records with no source at all)."""
    by_uuid = {r["uuid"]: r for r in missing}
    addr_idx: dict[str, list[str]] = {}
    street_idx: dict[str, list[str]] = {}
    for r in missing:
        a = r.get("address") or {}
        k = _addr_key(a.get("street") or "")
        addr_idx.setdefault(k + "|" + _norm(a.get("city") or ""), []).append(r["uuid"])
        street_idx.setdefault(k, []).append(r["uuid"])

    jobs: list[dict] = []
    seen: set[str] = set()

    for sec in split_sections(NSM10_MD):
        m = UUID_RE.search(sec["body"])
        if not m or m.group(1) not in by_uuid or m.group(1) in seen:
            continue
        meta = parse_heading(sec["heading"])
        meta["name"] = DASH_RE.split(sec["heading"], maxsplit=1)[0].strip()
        jobs.append({"uuid": m.group(1), "meta": meta, "heading": sec["heading"],
                     "body": sec["body"], "stem": f"DP_NSM10_{_safe(meta['name'])}",
                     "src": "NSM step-10 No-Response sweep, 2026-08-19"})
        seen.add(m.group(1))

    unresolved = []
    for sec in split_sections(HEIRS_MD):
        if sec["heading"].lower().startswith("not resolved"):
            continue
        meta = parse_heading(sec["heading"])
        k = _addr_key(meta["street"])
        hits = [u for u in (addr_idx.get(k + "|" + _norm(meta["city"]))
                            or street_idx.get(k) or []) if u not in seen]
        if len(hits) != 1:
            unresolved.append({"heading": sec["heading"], "hits": len(hits),
                               "body": sec["body"]})
            continue
        u = hits[0]
        meta["name"] = meta["name"] or (by_uuid[u].get("owner") or {}).get("last_name", "")
        stem = (f"DP_HeirsSweep_{_safe(meta['name'])}_"
                f"{meta['case'] or _safe(meta['street'])[:14]}")
        jobs.append({"uuid": u, "meta": meta, "heading": sec["heading"],
                     "body": sec["body"], "stem": stem,
                     "src": "Heirs-of backlog sweep, 2026-08-20"})
        seen.add(u)

    # ---- Tier 3: surname, only among what is still unclaimed, only if unique.
    # This is what rescues an estate whose DataSift property address is a
    # DIFFERENT parcel than the one the sweep worked -- Hines is filed on the
    # vacant "0 Wesley Woods Ln" lot while the sweep heading names the house on
    # Deal Rd, and Vance reads 2149 Brevard Place Rd against the sweep's 2137.
    # Uniqueness across ALL remaining records is the guard; anything ambiguous
    # stays unresolved rather than being filed on a stranger's estate.
    if unresolved:
        left = [r for r in missing if r["uuid"] not in seen]
        still = []
        for item in unresolved:
            meta = parse_heading(item["heading"])
            sur = _norm(meta["name"].split()[-1]) if meta["name"] else ""
            hits = [r for r in left
                    if sur and sur == _norm((r.get("owner") or {}).get("last_name") or "")
                    and r["uuid"] not in seen
                    and _owner_is_named_in(item["body"], r)]
            if len(hits) != 1:
                still.append(item)
                continue
            u = hits[0]["uuid"]
            a = hits[0].get("address") or {}
            meta["matched_by"] = "surname"
            meta["record_street"] = a.get("street") or ""
            stem = (f"DP_HeirsSweep_{_safe(meta['name'])}_"
                    f"{meta['case'] or _safe(meta['street'])[:14]}")
            jobs.append({"uuid": u, "meta": meta, "heading": item["heading"],
                         "body": item["body"], "stem": stem,
                         "src": "Heirs-of backlog sweep, 2026-08-20"})
            seen.add(u)
        unresolved = still

    # ---- Tier 4: the one-off standalone packs (DataFlik research, 8/19).
    # Their filename carries the address, not a case number, so they are keyed
    # off the address embedded in the stem.
    for md in sorted(REPORT_DIR.glob("DP_DataFlik_*.md")):
        m = re.match(r"DP_DataFlik_([A-Za-z]+)_(.+)", md.stem)
        if not m:
            continue
        key = _addr_key(re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", m.group(2)))
        hits = [u for u in (street_idx.get(key) or []) if u not in seen]
        if len(hits) != 1:
            continue
        body = md.read_text(encoding="utf-8", errors="replace")
        body = re.sub(r"\A#[^\n]*\n", "", body).strip()
        a = by_uuid[hits[0]].get("address") or {}
        jobs.append({"uuid": hits[0], "stem": md.stem,
                     "meta": {"name": m.group(1), "case": "",
                              "street": a.get("street") or "",
                              "city": a.get("city") or "", "county": ""},
                     "heading": m.group(1), "body": body,
                     "src": "DataFlik heir research, 2026-08-19"})
        seen.add(hits[0])

    orphans = [r for r in missing if r["uuid"] not in seen]
    return jobs, unresolved, orphans


def build(audit_only: bool) -> int:
    tok = token()
    if not tok:
        print("DataSift login failed")
        return 1
    h = headers(tok)

    recs = dp_complete_records(h)
    print(f"DP Complete records live: {len(recs)}")
    with ThreadPoolExecutor(max_workers=8) as ex:
        docs = list(ex.map(lambda r: documents(h, r["uuid"]), recs))
    errs = sum(1 for d in docs if d is None)
    missing = [r for r, d in zip(recs, docs) if d is not None and not d]
    print(f"  already attached: {sum(1 for d in docs if d)}"
          f"   MISSING a file: {len(missing)}   lookup errors: {errs}")

    jobs, unresolved, orphans = collect_jobs(missing)
    print(f"\nresolved to a record: {len(jobs)}"
          f"   ({sum(1 for j in jobs if j['src'].startswith('NSM'))} NSM10,"
          f" {sum(1 for j in jobs if j['src'].startswith('Heirs'))} heirs)")
    print(f"heirs sections with no clean record match: {len(unresolved)}")
    for u in unresolved[:12]:
        print(f"   [{u['hits']} hits] {u['heading']}")
    print(f"\nrecords with NO pack source: {len(orphans)}")
    for r in orphans[:20]:
        a, o = r.get("address") or {}, r.get("owner") or {}
        print(f"   {(a.get('street') or '')[:34]:34} {(a.get('city') or '')[:14]:14} "
              f"{o.get('first_name','')} {o.get('last_name','')}")

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(
        {"jobs": [{k: v for k, v in j.items() if k != "body"} for j in jobs],
         "unresolved": [{k: v for k, v in u.items() if k != "body"}
                        for u in unresolved],
         "orphans": [{"uuid": r["uuid"], **(r.get("address") or {}),
                      "owner": f"{(r.get('owner') or {}).get('first_name', '')} "
                               f"{(r.get('owner') or {}).get('last_name', '')}".strip()}
                     for r in orphans]}, indent=1), encoding="utf-8")

    if audit_only:
        print(f"\naudit only - wrote {STATE}")
        return 0

    PACK_DIR.mkdir(parents=True, exist_ok=True)
    from deep_prospect_pdf import render
    # Stems are built from the owner name, and the sweeps contain repeats (two
    # Smiths, two Whites). Left alone they silently overwrite each other -- the
    # first run wrote 196 manifest rows but only 190 files. Disambiguate with
    # the house number, then the uuid, so every record keeps its own pack.
    used: dict[str, int] = {}
    for j in jobs:
        stem = j["stem"]
        if stem in used:
            num = (j["meta"].get("street") or "").split(" ")[0]
            cand = f"{stem}_{_safe(num)}" if num else stem
            stem = cand if cand not in used else f"{stem}_{j['uuid'][:8]}"
        used[stem] = 1
        j["stem"] = stem

    manifest = []
    for j in jobs:
        md_path = PACK_DIR / f"{j['stem']}.md"
        md_path.write_text(pack_markdown(j["src"], j["meta"], j["heading"], j["body"]),
                           encoding="utf-8")
        manifest.append({"uuid": j["uuid"], "pdf": render(str(md_path)),
                         "stem": j["stem"], "street": j["meta"]["street"],
                         "city": j["meta"]["city"], "case": j["meta"]["case"]})
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\nbuilt {len(manifest)} pack PDF(s) in {PACK_DIR}")
    print(f"manifest: {MANIFEST}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="report only, build nothing")
    raise SystemExit(build(ap.parse_args().audit))


if __name__ == "__main__":
    main()
