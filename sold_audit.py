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
                    elif "decedent" in lv:
                        header["decedent"] = c_i
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
                "address": g("address"),
                "parcel": parcel,
            })
    print(f"Rows with parcels: {len(rows)}")
    return rows


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
            o = (owners[0] or {}) if owners else {}
            owner = (" ".join(str(o.get(k) or "") for k in
                              ("firstName", "lastName")).strip()
                     or str(o)[:60]) if o else ""
        else:
            owner = str(owners or "")[:60]
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
    print(f"\n=== FLAGGED: {len(flagged)} probate properties sold since {args.since} ===")
    for r in flagged:
        print(f"  {r['case'] or 'NO CASE#'} | {r['county'].title():12s} | "
              f"{r['decedent'][:30]:30s} | {r['address'][:35]:35s} | "
              f"sold {r.get('sale_date')} for {r.get('sale_price')}")


if __name__ == "__main__":
    main()
