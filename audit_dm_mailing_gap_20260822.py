"""READ-ONLY audit: which DP'd records still mail to the PROPERTY instead of the DM?

Prompted by Casto 26E000805-480 (2026-08-22): Oren saw a "DP Complete" record
whose contact card still read the property address while the DP pack named
"649 Haw Run Rd; Gay, WV". The 8/20 push DID carry mailing, but only when
parse_full_address() succeeded - its first dry run failed on 13 of 23 addresses
("mailing unchanged (no parseable DM address)"), and the 8/22 rename push
scoped mailing OUT by design. So the coverage was never verified end to end.

Sources of the EXPECTED DM mailing address:
  * output/dp_heirs_sweep_20260820/results.json  (dm.address + occupied_flag)
  * output/dp_nsm10_20260819/results.json        (dm_mail + uuid)
  * manual_corrections.csv "Mailing Address/City/State/Zip" rows (queued, and
    never pushed by any script - the rename push skips mailing by design)

The LIVE mailing address on a DataSift record is owner.address (the property
situs is the top-level address). verify_gaps_by_uuid_20260822.py read
owner["mailing_street"], which does not exist - that is why its "Owner Mailing"
column came back blank for all 10 rows.

Writes NOTHING. Every call is a GET / search.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\audit_dm_mailing_gap_20260822.py

Output: output/dm_mailing_gap_20260822.csv + console summary.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import re
import sys
import time as _time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import search, token  # noqa: E402

API = "https://apiv2.reisift.io"
OUT = REPO / "output" / "dm_mailing_gap_20260822.csv"
_LOG = open(REPO / "logs" / "audit_dm_mailing_gap_20260822.log", "a", encoding="utf-8")
_w = sys.stdout.write
sys.stdout.write = lambda t: (_w(t), _LOG.write(t), _LOG.flush())[0]

_SUFFIX = {"street": "st", "avenue": "ave", "av": "ave", "road": "rd",
           "drive": "dr", "lane": "ln", "court": "ct", "circle": "cir",
           "place": "pl", "boulevard": "blvd", "highway": "hwy", "trail": "trl",
           "parkway": "pkwy", "terrace": "ter", "north": "n", "south": "s",
           "east": "e", "west": "w"}


def norm(street: str) -> str:
    """Loose street key: no punctuation, common suffixes folded, unit dropped."""
    s = re.sub(r"[^a-z0-9 ]", " ", (street or "").lower())
    s = re.split(r"\b(?:apt|unit|ste|suite|lot)\b", s)[0]
    toks = [_SUFFIX.get(t, t) for t in s.split()]
    return " ".join(toks).strip()


def parse_expected(full: str) -> dict:
    """DM address -> {street, city, state, zip}. Two shapes are in the wild:

      sweep 8/20 (Enformion): '649 Haw Run Rd; Gay, WV 25244-9080'
      NSM10 8/19:             '3086 Montclair Dr, Claremont NC 28610-9604'

    The NSM10 shape has no comma before the state, which is why the first cut of
    this audit filed 122 rows as UNPARSEABLE.
    """
    parts = [p.strip() for p in (full or "").replace(";", ",").split(",") if p.strip()]
    if len(parts) < 2:
        return {}
    m = re.search(r"\b([A-Za-z]{2})\s+(\d{5})(?:-\d{4})?\s*$", parts[-1])
    if not m:
        return {}
    if len(parts) == 2:
        # tail is "City ST ZIP" - everything before the state token is the city
        city = parts[-1][:m.start()].strip().rstrip(",")
        return {"street": parts[0], "city": city,
                "state": m.group(1).upper(), "zip": m.group(2)}
    return {"street": ", ".join(parts[:-2]) if len(parts) > 3 else parts[0],
            "city": parts[-2], "state": m.group(1).upper(), "zip": m.group(2)}


def load_expected() -> list[dict]:
    """Every case a DP run found an off-site DM mailing address for."""
    want: dict[str, dict] = {}

    # --- 8/20 heirs backlog sweep -------------------------------------------
    p = REPO / "output" / "dp_heirs_sweep_20260820" / "results.json"
    for e in json.loads(p.read_text(encoding="utf-8")):
        if e.get("outcome") != "resolved":
            continue
        dm = e.get("dm") or {}
        key = e.get("case_no") or "street:" + str(e.get("property"))
        want[key] = {"case": e.get("case_no", ""), "src": "sweep 8/20",
                     "uuid": "", "property": e.get("property", ""),
                     "prop_city": e.get("property_city", ""),
                     "dm": (str(dm.get("first", "")) + " " + str(dm.get("last", ""))).strip(),
                     "expected_raw": dm.get("address") or "",
                     "occupied": bool(dm.get("occupied_flag"))}

    # --- 8/19 NSM10 no-response re-traces (these carry the uuid) ------------
    p = REPO / "output" / "dp_nsm10_20260819" / "results.json"
    for e in json.loads(p.read_text(encoding="utf-8")):
        mail = (e.get("dm_mail") or "").strip()
        if not mail:
            continue
        prop = e.get("property") or ""
        key = e.get("case_no") or "uuid:" + str(e.get("uuid"))
        want[key] = {"case": e.get("case_no", ""), "src": "NSM10 8/19",
                     "uuid": e.get("uuid", ""),
                     "property": prop.split(",")[0].strip(),
                     "prop_city": prop.split(",")[-1].strip() if "," in prop else "",
                     "dm": (str(e.get("dm_first", "")) + " " + str(e.get("dm_last", ""))).strip(),
                     "expected_raw": mail, "occupied": False}

    # --- queued-but-never-pushed mailing corrections -------------------------
    q: dict[str, dict[str, str]] = {}
    with (REPO / "manual_corrections.csv").open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 3:
                continue
            case, field, val = row[0].strip(), row[1].strip().lower(), row[2].strip()
            if field.startswith("mailing "):
                q.setdefault(case, {})[field[8:]] = val
    for case, m in q.items():
        if not m.get("address"):
            continue
        raw = (m["address"] + ", " + m.get("city", "") + ", "
               + m.get("state", "NC") + " " + m.get("zip", "")).replace(" ,", ",")
        if case in want and want[case].get("expected_raw"):
            want[case]["src"] += " + manual_corrections"
            continue
        want[case] = {"case": case, "src": "manual_corrections", "uuid": "",
                      "property": "", "prop_city": "", "dm": "",
                      "expected_raw": raw, "occupied": False}
    return list(want.values())


def get_prop(h: dict, uuid: str) -> dict:
    """GET with backoff - the API resets the connection under a long read loop."""
    for attempt in range(4):
        try:
            r = requests.get(API + "/api/internal/property/" + uuid + "/",
                             headers=h, timeout=30)
        except requests.exceptions.RequestException as e:  # noqa: BLE001
            print("    (conn error " + type(e).__name__ + ", retry "
                  + str(attempt + 1) + "/4)")
            _time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 429:
            _time.sleep(5 * (attempt + 1))
            continue
        if r.status_code != 200:
            return {}
        d = r.json()
        return d.get("data") or d.get("result") or d
    return {}


def search_retry(h: dict, text: str) -> list:
    for attempt in range(3):
        try:
            return search(h, text)
        except requests.exceptions.RequestException:
            _time.sleep(2 * (attempt + 1))
    return []


def find_uuid(h: dict, street: str, dm_last: str, manifest: dict) -> tuple[str, str]:
    """street -> uuid, via the DP-pack manifest first, then a search."""
    k = norm(street)
    if k and k in manifest:
        return manifest[k], "manifest"
    if not street:
        return "", "no street"
    num = (street.split() or [""])[0].lower()
    for q in [street] + ([dm_last] if dm_last else []):
        hits = search_retry(h, q)
        if not hits:
            continue
        if len(hits) == 1:
            return hits[0].get("uuid", ""), "search " + repr(q)
        exact = [x for x in hits
                 if norm((x.get("address") or {}).get("street") or "") == k]
        if len(exact) == 1:
            return exact[0].get("uuid", ""), "search " + repr(q) + " (filtered)"
        if num:
            byn = [x for x in hits if ((x.get("address") or {}).get("street") or "")
                   .lower().startswith(num + " ")]
            if len(byn) == 1:
                return byn[0].get("uuid", ""), "search " + repr(q) + " (house no)"
    return "", "NOT FOUND"


def main() -> int:
    print("\n===== DM mailing audit at " + str(_dt.datetime.now()) + " =====")
    exp = load_expected()
    print("cases with a DP-found DM mailing address: " + str(len(exp)))

    manifest: dict[str, str] = {}
    mp = REPO / "output" / "dp_pack_manifest_20260822.json"
    if mp.exists():
        for e in json.loads(mp.read_text(encoding="utf-8")):
            if e.get("street") and e.get("uuid"):
                manifest.setdefault(norm(e["street"]), e["uuid"])
    print("street->uuid shortcuts from DP pack manifest: " + str(len(manifest)))

    from audit_rename_gap_20260822 import case_addresses
    addrs = case_addresses()

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": "Bearer " + tok,
         "content-type": "application/json"}

    rows = []
    for e in sorted(exp, key=lambda x: (x["src"], x["case"] or x["property"])):
        street = e["property"] or addrs.get(e["case"], ("", ""))[0]
        want = parse_expected(e["expected_raw"])
        uuid, how = e["uuid"], "given"
        if not uuid:
            uuid, how = find_uuid(h, street, (e["dm"].split() or [""])[-1], manifest)

        live_mail = live_prop = live_owner = ""
        if not uuid:
            status = "NOT FOUND"
        else:
            d = get_prop(h, uuid)
            o = d.get("owner") or {}
            oa = o.get("address") or {}
            pa = d.get("address") or {}
            live_owner = ((o.get("first_name") or "").strip() + " "
                          + (o.get("last_name") or "").strip()).strip()
            live_mail = ", ".join(x for x in [
                oa.get("street"), oa.get("city"),
                ((oa.get("state") or "") + " " + (oa.get("postal_code") or "")).strip()] if x)
            live_prop = ", ".join(x for x in [pa.get("street"), pa.get("city")] if x)
            lm, lp = norm(oa.get("street") or ""), norm(pa.get("street") or "")
            wm = norm(want.get("street") or "")
            if not d:
                status = "GET FAILED"
            elif e["occupied"]:
                status = "OK (DM at property)"
            elif not want:
                status = "UNPARSEABLE DP ADDRESS"
            elif not lm:
                status = "GAP - no mailing on record"
            elif lm == wm:
                status = "OK"
            elif lm == lp:
                status = "GAP - mails to property"
            else:
                status = "DIFFERENT (review)"

        print("  " + (e["case"] or street)[:22].ljust(22) + " " + status.ljust(26)
              + " live=" + repr(live_mail[:34]).ljust(36)
              + " want=" + repr((want.get("street") or e["expected_raw"])[:28]))
        rows.append({"Case No.": e["case"], "Status": status, "Source": e["src"],
                     "DM": e["dm"], "Live Owner": live_owner,
                     "Property": live_prop or (street + ", " + e["prop_city"]).strip(", "),
                     "Live Mailing": live_mail,
                     "DP Says Mailing": e["expected_raw"],
                     "UUID": uuid, "Found via": how})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["Status"]] = counts.get(r["Status"], 0) + 1
    print("\n==== SUMMARY ====")
    for k in sorted(counts, key=lambda x: -counts[x]):
        print("  " + k.ljust(28) + " " + str(counts[k]))
    bad = [r for r in rows if r["Status"].startswith("GAP")]
    if bad:
        print("\nMAILS TO PROPERTY / NO MAILING (" + str(len(bad)) + "):")
        for r in bad:
            print("  " + (r["Case No."] or r["Property"])[:22].ljust(22) + " "
                  + r["DM"].ljust(24) + " should mail -> " + r["DP Says Mailing"]
                  + "   " + r["UUID"])
    print("\nwrote " + str(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
