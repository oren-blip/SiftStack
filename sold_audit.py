"""Recently-sold loss audit — parcel-level ground truth from county GIS.

Reads every week tab of the latest consolidated FTM workbook, dedupes
parcels, queries each county's GIS BY PARCEL ID (exact match — no address
fuzz), and reports any probate property whose GIS sale date falls on/after
--since (default 2026-06-01). Independent of DataSift entirely.

Usage:
    python sold_audit.py                       # since 2026-06-01
    python sold_audit.py --since 2026-01-01    # any 2026 sale
Output: output/sold_audit_<today>.csv + console summary (Case No. included).
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import requests  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from nc_gis_lookup import (  # noqa: E402
    _ARCGIS_CONFIG, _ARCGIS_HEADERS, _catawba_parcel_report,
    _parse_arcgis_sale_date, _parse_arcgis_sale_price, _polaris3g_get_page,
)

ARC_COUNTIES = {"rowan", "cabarrus", "gaston", "iredell", "lincoln"}


def load_rows() -> list[dict]:
    books = sorted(glob.glob("output/FTM_*_NC_Estates_throughWeek*.xlsx"),
                   key=os.path.getmtime)
    if not books:
        raise SystemExit("No consolidated workbook found in output/")
    book = books[-1]
    print(f"Workbook: {book}")
    wb = load_workbook(book, read_only=True, data_only=True)
    rows: list[dict] = []
    for ws in wb.worksheets:
        header: dict[str, int] = {}
        for r_i, row in enumerate(ws.iter_rows(values_only=True)):
            vals = ["" if v is None else str(v).strip() for v in row]
            if not header:
                for c_i, v in enumerate(vals):
                    lv = v.lower()
                    if "county" == lv:
                        header["county"] = c_i
                    elif "case" in lv and "no" in lv:
                        header["case"] = c_i
                    elif "parcel" in lv:
                        header["parcel"] = c_i
                    elif lv.startswith("property address"):
                        header["address"] = c_i
                    elif "deceased" in lv or lv == "decedent":
                        header["decedent"] = c_i
                    elif lv.startswith("personal representative"):
                        header["pr"] = c_i
                    elif lv == "file date":
                        header["filed"] = c_i
                if header and "parcel" not in header:
                    header = {}
                continue
            def g(key):
                i = header.get(key)
                return vals[i] if i is not None and i < len(vals) else ""
            county = g("county").lower()
            parcel = g("parcel")
            if not county or not parcel:
                continue
            rows.append({
                "week": ws.title,
                "county": county,
                "case": g("case"),
                "decedent": g("decedent"),
                "pr": g("pr"),
                "filed": g("filed"),
                "address": g("address"),
                "parcel": parcel,
            })
    print(f"Rows with parcels: {len(rows)}")
    return rows


_ENTITY_MARKERS = (
    "LLC", "L L C", "INC", "CORP", "PROPERTIES", "HOLDINGS", "HOMES",
    "INVESTMENTS", "CAPITAL", "VENTURES", "REALTY", "REI", "GROUP",
    "PARTNERS", "ENTERPRISES", "SOLUTIONS", "TRUST CO",
)


def _surnames(name: str) -> set[str]:
    return {t.strip(",.").upper() for t in name.replace(",", " ").split()
            if len(t.strip(",.")) > 2}


def classify(row: dict) -> str:
    """HEIR TRANSFER / INVESTOR PURCHASE / MARKET SALE / UNCLEAR TRANSFER."""
    owner = (row.get("owner") or "").upper()
    fam = _surnames(row.get("decedent", "")) | _surnames(row.get("pr", ""))
    if fam & _surnames(owner):
        return "HEIR TRANSFER"
    if any(m in owner for m in _ENTITY_MARKERS):
        return "INVESTOR PURCHASE"
    price = row.get("sale_price")
    try:
        pricef = float(price) if price not in (None, "") else 0.0
    except (TypeError, ValueError):
        pricef = 0.0
    if pricef >= 5000:
        return "MARKET SALE"
    return "UNCLEAR TRANSFER"


def update_competitor_log(flagged: list[dict]) -> None:
    """Append investor/market sales to a durable competitor log (dedup by case)."""
    path = "output/competitor_log.csv"
    existing: set[str] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            existing = {r["case"] for r in csv.DictReader(f)}
    new = [r for r in flagged
           if r["class"] in ("INVESTOR PURCHASE", "MARKET SALE")
           and r["case"] not in existing]
    if not new:
        print("Competitor log: no new entries")
        return
    write_header = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[
            "found", "case", "county", "decedent", "filed", "address",
            "sale_date", "sale_price", "buyer", "class", "week"],
            extrasaction="ignore")
        if write_header:
            w.writeheader()
        for r in new:
            w.writerow({**r, "found": date.today().isoformat(),
                        "buyer": r.get("owner", "")})
    print(f"Competitor log: +{len(new)} entries -> {path}")


def norm_pid(pid: str) -> str:
    """Strip float artifacts ('4673892477.00000000') and whitespace."""
    pid = pid.strip()
    if re.fullmatch(r"\d+\.0+", pid):
        pid = pid.split(".")[0]
    return pid


# Candidate (field, mode) query attempts per county, in order. Older workbook
# weeks recorded the ALTERNATE id type for Gaston (PIN, pre-2026-07-09) and
# Lincoln (PIN, pre-2026-07-23); Cabarrus workbook holds the 10-digit PIN
# while the GIS canonical field is 14-digit PIN14 (prefix match); Iredell
# PINs are sometimes stored dashed.
_FIELD_ATTEMPTS: dict[str, list[tuple[str, str]]] = {
    "rowan":    [("PARCEL_ID", "exact")],
    "cabarrus": [("PIN14", "exact"), ("PIN14", "like")],
    "gaston":   [("PID", "exact"), ("PIN", "exact")],
    "iredell":  [("PIN", "exact"), ("PIN", "like"), ("PIN", "dashed")],
    "lincoln":  [("PARCELID", "exact"), ("PIN", "exact")],
}


def q_arcgis(county: str, pid: str) -> dict | None:
    cfg = _ARCGIS_CONFIG[county]
    pid = norm_pid(pid)
    pid_esc = pid.replace("'", "''")
    attempts = _FIELD_ATTEMPTS.get(county, [(cfg["parcel_field"], "exact")])
    for field, mode in attempts:
        if mode == "exact":
            where = f"{field}='{pid_esc}'"
        elif mode == "like":
            where = f"{field} LIKE '{pid_esc}%'"
        elif mode == "dashed" and len(pid) == 10:
            dashed = f"{pid[:4]}-{pid[4:6]}-{pid[6:]}"
            where = f"{field}='{dashed}'"
        else:
            continue
        try:
            r = requests.get(f"{cfg['url']}/query", params={
                "where": where,
                "outFields": "*", "returnGeometry": "false", "f": "json",
            }, headers=_ARCGIS_HEADERS, timeout=30)
            data = r.json() or {}
            if data.get("error"):
                continue  # invalid field on this layer — try next
            feats = data.get("features", [])
            if not feats:
                continue
            attrs = feats[0].get("attributes", {})
            owner = " / ".join(
                str(attrs.get(f) or "").strip()
                for f in cfg.get("owner_fields", []) if attrs.get(f))
            return {
                "sale_date": _parse_arcgis_sale_date(attrs),
                "sale_price": _parse_arcgis_sale_price(attrs),
                "owner": owner,
            }
        except Exception as e:  # noqa: BLE001
            print(f"  ! {county} {pid} ({field} {mode}): {e}")
    return None


def q_catawba(pid: str) -> dict | None:
    try:
        rec = _catawba_parcel_report(pid)
        if not rec:
            return None
        sd = str(rec.get("sale_date") or "")[:10] or None
        if sd and "/" in sd:
            m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", sd)
            if m:
                sd = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        price = rec.get("sale_amount")
        try:
            price = float(price) if price not in (None, "") else None
        except (TypeError, ValueError):
            price = None
        owner = str(rec.get("owner") or rec.get("owner_name") or "").strip()
        return {"sale_date": sd, "sale_price": price, "owner": owner}
    except Exception as e:  # noqa: BLE001
        print(f"  ! catawba {pid}: {e}")
        return None


_meck_session = None
_meck_supported = True


def q_meck(pid: str) -> dict | None:
    """polaris3g bolt parcel lookup — the param is `pid` (verified 2026-08-01;
    record includes sale_date, sale_price, sale_qualified, owner, situs)."""
    global _meck_session
    if _meck_session is None:
        _meck_session = requests.Session()
    try:
        rows = _polaris3g_get_page(_meck_session, {"pid": norm_pid(pid)})
        if not rows:
            return None
        rec = rows[0]
        sd = str(rec.get("sale_date") or "")[:10] or None
        if sd and "/" in sd:
            m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", sd)
            if m:
                sd = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        owners = rec.get("owner")
        if isinstance(owners, list):
            parts = []
            for o in owners[:3]:
                if isinstance(o, dict):
                    nm = (o.get("fullname")
                          or " ".join(str(o.get(k) or "") for k in
                                      ("firstname", "firstName",
                                       "lastname", "lastName")).strip())
                    if nm:
                        parts.append(str(nm))
                elif o:
                    parts.append(str(o))
            owner = " / ".join(parts)[:80]
        elif isinstance(owners, dict):
            owner = str(owners.get("fullname") or owners)[:80]
        else:
            owner = str(owners or "")[:80]
        price = rec.get("sale_price")
        try:
            price = float(price) if price not in (None, "") else None
        except (TypeError, ValueError):
            price = None
        return {"sale_date": sd, "sale_price": price, "owner": owner}
    except Exception as e:  # noqa: BLE001
        print(f"  ! mecklenburg {pid}: {e}")
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-06-01")
    args = ap.parse_args()

    rows = load_rows()
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["county"], r["parcel"])
        seen.setdefault(key, r)  # keep first (oldest week) occurrence
    print(f"Unique (county, parcel): {len(seen)}")

    results = []
    stats: dict[str, list[int]] = {}
    for i, ((county, pid), r) in enumerate(sorted(seen.items()), 1):
        if county in ARC_COUNTIES:
            gis = q_arcgis(county, pid)
        elif county == "catawba":
            gis = q_catawba(pid)
        elif county == "mecklenburg":
            gis = q_meck(pid)
        else:
            gis = None
        st = stats.setdefault(county, [0, 0, 0])  # [queried, found, flagged]
        st[0] += 1
        flag = ""
        if gis:
            st[1] += 1
            sd = gis.get("sale_date")
            if sd and sd >= args.since:
                flag = f"SOLD since {args.since}"
                st[2] += 1
        results.append({**r, **(gis or {}), "flag": flag})
        if i % 50 == 0:
            print(f"  ...{i}/{len(seen)}")
        time.sleep(0.3)

    out_path = f"output/sold_audit_{date.today().isoformat()}.csv"
    results.sort(key=lambda x: (x["flag"] == "", x["county"]))
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[
            "flag", "county", "case", "decedent", "parcel", "address",
            "sale_date", "sale_price", "owner", "week"], extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"\nWrote {out_path}")

    print("\n=== Coverage (queried / found in GIS / flagged sold) ===")
    for county, (q, f_, fl) in sorted(stats.items()):
        print(f"  {county:12s} {q:4d} / {f_:4d} / {fl}")
    flagged = [r for r in results if r["flag"]]
    for r in flagged:
        r["class"] = classify(r)
    print(f"\n=== FLAGGED: {len(flagged)} probate properties transferred since {args.since} ===")
    for r in flagged:
        print(f"  {r['case'] or 'NO CASE#'} | {r['county'].title():12s} | "
              f"{r['decedent'][:26]:26s} | {r['address'][:32]:32s} | "
              f"{r.get('sale_date')} | {str(r.get('sale_price') or ''):>9s} | {r['class']}")

    update_competitor_log(flagged)

    # Heir-transfer retarget CSV — new owner already holds clear title.
    heirs = [r for r in flagged if r["class"] == "HEIR TRANSFER"]
    if heirs:
        hpath = f"output/heir_transfers_{date.today().isoformat()}.csv"
        with open(hpath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "case", "county", "decedent", "pr", "filed", "address",
                "sale_date", "owner", "week"], extrasaction="ignore")
            w.writeheader()
            w.writerows(heirs)
        print(f"Heir-transfer retarget list: {len(heirs)} -> {hpath}")


if __name__ == "__main__":
    main()
