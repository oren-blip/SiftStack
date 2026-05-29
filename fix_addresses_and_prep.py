"""One-shot: re-lookup property addresses for rows with parcel-but-no-address
(fixes the 5-digit-street-number-misparsed-as-ZIP bug now patched in
nc_gis_lookup._candidate_to_address_parts), then run the DataSift prep
(drop no-parcel + heirs-of rewrite). Writes fresh timestamped output.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nc_gis_lookup import (  # noqa: E402
    _candidate_to_address_parts,
    _name_match_score,
    lookup_properties,
    simplify_use_code,
    split_decedent_name,
)
from reenrich_ftm_executors import write_csv, write_xlsx  # noqa: E402


_PARCEL_PROPERTY_FIELDS = (
    "Parcel ID", "Property Address", "Property City",
    "Property State", "Property Zip", "Property use",
)


def _name_variations(decedent: str) -> list[str]:
    """Variations to try when re-searching for the correct parcel.

    Order matters: the first variation that returns matches wins, and
    every variation we try costs another GIS round-trip. User rule:
    always try "LAST FIRST MIDDLE" first — that's the format the
    county GIS owner-search indices return most reliably.
    """
    first, mid, last = split_decedent_name(decedent)
    raw = [
        f"{last} {first} {mid}".strip() if (last and first and mid) else None,
        decedent,
        f"{first} {mid} {last}".strip() if (first and mid and last) else None,
        last if last else None,
    ]
    seen: set[str] = set()
    out: list[str] = []
    for v in raw:
        v_norm = (v or "").strip()
        if v_norm and v_norm.upper() not in seen:
            seen.add(v_norm.upper())
            out.append(v_norm)
    return out


def research_blank_parcels(
    rows: list[dict],
    min_score: float = 0.7,
    audit_rejected_pids: set[tuple[str, str]] | None = None,
) -> int:
    """For rows where Parcel ID is blank but we have a decedent name + county,
    re-search the county GIS with name variations and try to find the
    correct parcel using the middle-name-aware matcher. Recovers cases
    where the original (buggy-matcher) scrape picked the wrong parcel
    and the audit then blanked it — e.g. Osborne, James Lee → correct
    parcel exists but original search picked the wrong James D Osborne.

    `audit_rejected_pids` (set of (county_lower, pid)) is a blacklist:
    when the audit step just rejected a PID for this decedent because
    the GIS owner doesn't match (e.g. property held by a family trust,
    not the decedent personally), the re-search must NOT pick up that
    same PID under a broader name variation — that's how
    "Walker, Betty Louise" kept getting re-bound to the same Walker
    Family Trust parcel after the audit had explicitly rejected it.
    """
    from nc_gis_lookup import filter_for_lead_quality
    rejected = audit_rejected_pids or set()
    recovered = 0
    for r in rows:
        if (r.get("Parcel ID") or "").strip():
            continue
        dec = (r.get("Deceased Owner") or "").strip()
        county = (r.get("County") or "").strip()
        if not dec or not county or "IN THE MATTER" in dec.upper():
            continue
        found = None
        used_variation = ""
        for v in _name_variations(dec):
            try:
                results = lookup_properties(v, county, min_score=min_score)
            except Exception:
                continue
            if not results:
                continue
            kept = filter_for_lead_quality(results)
            # Drop any candidate whose PID was just rejected by the audit
            kept = [c for c in kept if (county.lower(), c.pid or "") not in rejected]
            if not kept:
                continue
            best = max(kept, key=lambda c: c.market_value or 0)
            found = best
            used_variation = v
            break
        if not found:
            continue
        street, city, zipc = _candidate_to_address_parts(found)
        r["Parcel ID"] = found.pid or ""
        r["Property Address"] = street
        r["Property City"] = city
        r["Property State"] = "NC"
        r["Property Zip"] = zipc
        if found.use_code:
            new_use = simplify_use_code(found.use_code, found.use_description, found.county)
            if new_use:
                r["Property use"] = new_use
        print(f"  Re-found {county}/{dec} via {used_variation!r}: {found.pid} {street}, {city} NC {zipc}")
        recovered += 1
    return recovered


def validate_existing_matches(
    rows: list[dict], min_score: float = 0.7,
) -> tuple[int, set[tuple[str, str]]]:
    """Re-score each parceled row's GIS match with the current matcher.
    Blank the parcel + property fields on rows where the match no longer
    passes — these were false-positive homonym matches under the OLD
    matcher (e.g. "James Lee Osborne" vs "JAMES D OSBORNE").

    Returns (blanked_count, rejected_pids) where rejected_pids is a set
    of (county_lower, pid) tuples that the re-search step should treat
    as a blacklist — see research_blank_parcels.
    """
    # Group rows by (county, decedent) so we only call lookup_properties
    # once per unique decedent (most have a single parcel anyway).
    from collections import defaultdict
    by_decedent: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if not (r.get("Parcel ID") or "").strip():
            continue
        dec = (r.get("Deceased Owner") or "").strip()
        county = (r.get("County") or "").strip()
        if not dec or not county or "IN THE MATTER" in dec.upper():
            continue
        by_decedent[(county, dec)].append(r)

    blanked = 0
    rejected_pids: set[tuple[str, str]] = set()
    for (county, dec), parcel_rows in by_decedent.items():
        try:
            # Use a wide min_score so we get ALL candidates including ones
            # that scored above 0.4 (lastname-only) under the old matcher
            results = lookup_properties(dec, county, min_score=0.4)
        except Exception as e:
            print(f"  ERROR validating {dec}: {e}")
            continue
        # Index candidates by pid
        by_pid = {c.pid: c for c in results}
        for r in parcel_rows:
            pid = r["Parcel ID"]
            cand = by_pid.get(pid)
            if cand is None:
                # Parcel ID no longer in result set — keep as-is (could be
                # data drift); print warning so user can spot-check
                print(f"  STALE {county}/{dec} pid={pid}: not in current GIS results")
                continue
            new_score = _name_match_score(dec, cand.owner_name)
            if new_score < min_score:
                print(f"  REJECT {county}/{dec} pid={pid}: owner={cand.owner_name!r} "
                      f"score={new_score:.2f} (was accepted under old matcher)")
                # Blank the parcel + property fields so prepare_for_datasift
                # treats this as a no-parcel row and drops it
                for col in _PARCEL_PROPERTY_FIELDS:
                    r[col] = ""
                blanked += 1
                rejected_pids.add((county.lower(), pid))
    return blanked, rejected_pids


# Property uses that we treat as "verify" because the original Cabarrus
# 'I' code (improved-but-no-detail) used to map to Commercial before the
# per-county short-circuit landed. Re-fetching them re-runs the now-fixed
# classifier.
_SUSPECT_USES = {"COMMERCIAL", "INDUSTRIAL", "OFFICE"}


def repair_addresses(rows: list[dict]) -> int:
    """Re-lookup property fields (street/city/zip + use) for rows where
    the original GIS data was incomplete, mangled by the old situs-parser
    bug, or pre-fix-era misclassified as Commercial.
    """
    repaired = 0
    for r in rows:
        pid = (r.get("Parcel ID") or "").strip()
        if not pid:
            continue
        prop_addr = (r.get("Property Address") or "").strip()
        prop_zip = (r.get("Property Zip") or "").strip()
        prop_use = (r.get("Property use") or "").strip()
        suspect_use = prop_use.upper() in _SUSPECT_USES
        # Re-fetch if anything is missing OR if Property use is suspect
        if prop_addr and prop_zip and prop_use and not suspect_use:
            continue
        dec = (r.get("Deceased Owner") or "").strip()
        county = (r.get("County") or "").strip()
        if not dec or "IN THE MATTER" in dec.upper():
            continue
        try:
            results = lookup_properties(dec, county, min_score=0.5)
        except Exception as e:
            print(f"  ERROR for {dec}: {e}")
            continue
        match = next((c for c in results if c.pid == pid), None)
        if not match:
            print(f"  No matching parcel {pid} in fresh lookup for {dec}")
            continue
        street, city, zipc = _candidate_to_address_parts(match)
        changed: list[str] = []
        if street and not prop_addr:
            r["Property Address"] = street
            r["Property City"] = city
            r["Property State"] = "NC"
            changed.append("addr")
        if zipc and not prop_zip:
            r["Property Zip"] = zipc
            changed.append("zip")
        if match.use_code:
            new_use = simplify_use_code(match.use_code, match.use_description, match.county)
            if new_use and (not prop_use or (suspect_use and new_use.upper() not in _SUSPECT_USES)):
                old = prop_use
                r["Property use"] = new_use
                changed.append(f"use({old!r}->{new_use!r})" if old else "use")
        if changed:
            print(f"  Fixed {r['County']} {pid}: {','.join(changed)} -> "
                  f"{r['Property Address']}, {r['Property City']} NC {r['Property Zip']} "
                  f"[{r.get('Property use', '')}]")
            repaired += 1
    return repaired


_BAD_CITY_TOKENS = {
    "DR","ST","RD","LN","CT","AVE","BLVD","WAY","CIR","PL","TC","TER","TR","TRL","PKWY","HWY",
    "N","S","E","W","NE","NW","SE","SW",
}
_US_STATE_CODES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA",
    "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC",
}


def clean_bad_city_zip_in_place(rows: list[dict]) -> tuple[int, int]:
    """Final cleanup: when Property City contains a street-type suffix
    (Dr/St/Rd/Ln/etc.), a state code (Ga/Ny/etc.), or a numeric value,
    it's leftover noise from an upstream parser bug — merge the street
    suffix back into Property Address (when applicable) and clear the
    bad value. Wrong city data is worse than blank — DataSift's Smarty
    will populate blanks on upload, but can't undo wrong values.

    Also reformat 9-digit-no-dash ZIPs (e.g., 281640000) to '28164-0000'
    or '28164' when the +4 portion is all zeros.

    Returns (cities_cleaned, zips_cleaned).
    """
    cleaned_city = 0
    cleaned_zip = 0
    for r in rows:
        city = (r.get("Property City") or "").strip()
        city_upper = city.upper()
        is_bad_city = (
            city_upper in _BAD_CITY_TOKENS
            or city_upper in _US_STATE_CODES
            or (city and city.replace("-", "").isdigit())
        )
        if is_bad_city:
            addr = (r.get("Property Address") or "").strip()
            if city_upper in _BAD_CITY_TOKENS and addr and not addr.upper().endswith(" " + city_upper):
                r["Property Address"] = f"{addr} {city}"
            r["Property City"] = ""
            cleaned_city += 1
        # ZIP normalization
        z = (r.get("Property Zip") or "").strip()
        if z and len(z) == 9 and z.isdigit():
            if z[5:] == "0000":
                r["Property Zip"] = z[:5]
            else:
                r["Property Zip"] = f"{z[:5]}-{z[5:]}"
            cleaned_zip += 1
        # Other bad-format ZIPs (not 5-digit or 5-4): clear
        z2 = (r.get("Property Zip") or "").strip()
        valid_zip = (len(z2) == 5 and z2.isdigit()) or (
            len(z2) == 10 and z2[5] == "-" and z2[:5].isdigit() and z2[6:].isdigit()
        )
        if z2 and not valid_zip:
            r["Property Zip"] = ""
            cleaned_zip += 1
    return cleaned_city, cleaned_zip


def _money(v) -> float:
    """Parse a market-value string to float ($ signs, commas tolerated). 0 if blank."""
    if v is None:
        return 0.0
    s = str(v).replace("$", "").replace(",", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def populate_property_values(rows: list[dict]) -> int:
    """Backfill Property Value from a fresh GIS lookup for rows that have a
    Parcel ID but no Property Value populated yet. Required before the
    drop_over_500k filter can run.
    """
    filled = 0
    for r in rows:
        pid = (r.get("Parcel ID") or "").strip()
        if not pid:
            continue
        if (r.get("Property Value") or "").strip():
            continue
        dec = (r.get("Deceased Owner") or "").strip()
        county = (r.get("County") or "").strip()
        if not dec or not county or "IN THE MATTER" in dec.upper():
            continue
        try:
            results = lookup_properties(dec, county, min_score=0.5)
        except Exception:
            continue
        match = next((c for c in results if c.pid == pid), None)
        if match and match.market_value:
            r["Property Value"] = f"{int(round(float(match.market_value))):,}"
            filled += 1
    return filled


def drop_over_500k(rows: list[dict], cap: float = 500_000) -> tuple[list[dict], int]:
    """Drop rows whose Property Value exceeds the cap. Skips rows without
    a populated value (we don't want to drop rows we couldn't price).
    """
    kept = [r for r in rows if _money(r.get("Property Value")) <= cap or not (r.get("Property Value") or "").strip()]
    dropped = len(rows) - len(kept)
    return kept, dropped


MANUAL_INDEX_PATH = Path("output") / ".manual_archive_index.json"


def _name_token_key(name: str) -> str:
    """Order-independent name key — covers 'Last, First Middle' /
    'First Middle Last' / 'AKA <alt>' variations. Must match
    build_manual_archive_index.py:name_token_key.
    """
    s = (name or "").upper()
    s = re.sub(r"\bAKA\b.*", "", s)
    s = re.sub(r"\b(JR|SR|II|III|IV|MR|MRS|MS|DR)\.?\b", "", s)
    tokens = sorted(t for t in re.findall(r"[A-Z]+", s) if len(t) >= 3)
    return " ".join(tokens)


def _parse_file_date_str(s: str) -> datetime | None:
    """Parse a 'File Date' cell value to datetime (MM/DD/YYYY or YYYY-MM-DD)."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _current_iso_week(rows: list[dict]) -> str | None:
    """Derive the ISO week tag (e.g. 'Week 21') from the most common File
    Date in this batch. Returns None when no parseable dates exist.
    """
    from collections import Counter
    counts: Counter[int] = Counter()
    for r in rows:
        d = _parse_file_date_str(r.get("File Date", ""))
        if d:
            counts[d.isocalendar().week] += 1
    if not counts:
        return None
    return f"Week {counts.most_common(1)[0][0]}"


def backfill_from_manual_archive(rows: list[dict]) -> tuple[int, int]:
    """Compare each row against the manual XLSX archive of prior pulls.

    - Blank-case-no row + archive match → backfill case# + flag as duplicate
    - Has-case-no row + archive match in a PRIOR week → flag as duplicate
    - No match → no-op

    Rows flagged as duplicates carry `_archive_duplicate = True` for the
    downstream `drop_archive_duplicates` step to remove.

    Returns (backfilled_or_flagged, no_match_count).
    """
    import json
    if not MANUAL_INDEX_PATH.exists():
        print(f"  Manual archive index not found ({MANUAL_INDEX_PATH}). "
              f"Run build_manual_archive_index.py first.")
        return (0, 0)
    with MANUAL_INDEX_PATH.open(encoding="utf-8") as f:
        archive = json.load(f).get("_entries", {})

    current_week = _current_iso_week(rows)
    if current_week:
        print(f"  Current scrape ISO week (from file dates): {current_week}")

    backfilled = 0
    no_match = 0
    for r in rows:
        dec = (r.get("Deceased Owner") or "").strip()
        county = (r.get("County") or "").strip()
        if not dec or not county:
            continue
        key = f"{county.upper()}||{_name_token_key(dec)}"
        entry = archive.get(key)
        if not entry:
            if not (r.get("Case No.") or "").strip():
                no_match += 1
            continue
        # Match found — decide whether it's a cross-week duplicate
        archive_week = entry.get("week", "")
        is_blank_case = not (r.get("Case No.") or "").strip()
        is_prior_week = current_week and archive_week and archive_week != current_week
        if not is_blank_case and not is_prior_week:
            continue  # current week archive match — keep, not a dupe

        if is_blank_case:
            # Backfill the case number from archive
            r["Case No."] = entry.get("case_no", "")
        # Backfill missing PR/mailing fields when archive has them and ours are blank
        for archive_key, csv_col in [
            ("first_name", "First Name"),
            ("last_name", "Last Name"),
            ("mailing_address", "Mailing Address"),
            ("mailing_city", "Mailing City"),
            ("mailing_state", "Mailing State"),
            ("mailing_zip", "Mailing Zip"),
            ("parcel_id", "Parcel ID"),
            ("property_address", "Property Address"),
            ("property_city", "Property City"),
            ("property_zip", "Property Zip"),
        ]:
            if not (r.get(csv_col) or "").strip() and entry.get(archive_key):
                r[csv_col] = entry[archive_key]
        # Tag the row so user can see it came from archive
        existing_tags = (r.get("Tags") or "").strip()
        marker = f"manual-archive:{entry.get('week', '?')}"
        if marker not in existing_tags:
            r["Tags"] = f"{existing_tags} | {marker}" if existing_tags else marker
        # Mark for drop — these are cross-week duplicates: the case was
        # filed weeks ago and the user already has it in their pipeline.
        # The current row is just the newspaper-published Notice-to-
        # Creditors which doesn't add value.
        r["_archive_duplicate"] = True
        print(f"  Archive match (drop as cross-week dupe): {county}/{dec!r} -> "
              f"case {entry['case_no']} (from {entry.get('week', '?')})")
        backfilled += 1
    return backfilled, no_match


def drop_archive_duplicates(rows: list[dict]) -> tuple[list[dict], int]:
    """Drop rows that were backfilled from the manual archive.
    These represent cases already in the user's prior-week pipeline —
    keeping them here would create duplicate uploads to DataSift.
    """
    kept = [r for r in rows if not r.get("_archive_duplicate")]
    dropped = len(rows) - len(kept)
    # Strip the private marker from kept rows for cleanliness
    for r in kept:
        r.pop("_archive_duplicate", None)
    return kept, dropped


def _norm_dec_name(name: str) -> tuple[str, str]:
    """Return (last_name, first_name) normalized for cross-source matching.
    Handles both 'Last, First Middle' and 'First Middle Last' formats, and
    common newspaper-publishing parser quirks like 'Jr, Floyd David Long'.
    """
    name = (name or "").strip()
    if not name:
        return ("", "")
    # Strip 'Aka X Y Z' aliases — keep the primary name
    if " AKA " in name.upper():
        name = re.split(r"\s+AKA\s+", name, flags=re.IGNORECASE, maxsplit=1)[0].strip()
    # Strip noise tokens (JR / SR / II / III) that the newspaper parser sometimes
    # treats as a separate "name" element
    noise = {"JR", "JR.", "SR", "SR.", "II", "III", "IV"}
    tokens = re.split(r"[,\s]+", name)
    tokens = [t.strip().upper() for t in tokens if t.strip() and t.strip().upper() not in noise]
    if not tokens:
        return ("", "")
    # Heuristic: in our scraper data, last name is usually:
    #  - First token if format was "Last, First Middle" (comma split)
    #  - Last token if format was "First Middle Last"
    # We try both and let the caller match on either order.
    return (tokens[0], tokens[-1])


def _dec_name_tokens(name: str) -> set[str]:
    """Return the full set of meaningful name tokens for subset/superset
    matching. Strips JR/SR/aliases like _norm_dec_name but keeps middle
    names — useful for catching newspaper-truncated rows like
    'Walker, Betty' that match the eCourts row 'Walker, Betty Louise'.
    """
    name = (name or "").strip()
    if not name:
        return set()
    if " AKA " in name.upper():
        name = re.split(r"\s+AKA\s+", name, flags=re.IGNORECASE, maxsplit=1)[0].strip()
    noise = {"JR", "JR.", "SR", "SR.", "II", "III", "IV"}
    return {
        t.strip().upper() for t in re.split(r"[,\s]+", name)
        if t.strip() and t.strip().upper() not in noise
    }


def soft_dedup_blank_case_no(rows: list[dict]) -> tuple[list[dict], int, int]:
    """For rows with blank Case No. (newspaper-published notices), check if
    the same decedent already exists as a named-case row in the same county.
    If so, MERGE: drop the blank row, but copy any fields the named row was
    missing (e.g., PR mailing that newspaper had but eCourts didn't).

    Returns (rows, merged_count, kept_unique_count).
    """
    import re as _re  # local alias because fn defined inside file
    named = [r for r in rows if (r.get("Case No.") or "").strip()]
    blanks = [r for r in rows if not (r.get("Case No.") or "").strip()]

    # Build lookup: by (county, last_name_tokens)
    named_by_key: dict[tuple[str, str], list[dict]] = {}
    for r in named:
        last, first = _norm_dec_name(r.get("Deceased Owner", ""))
        for tok in (last, first):  # try both orderings
            if tok:
                named_by_key.setdefault((r["County"], tok), []).append(r)

    merged = 0
    to_drop_ids: set[int] = set()
    for b in blanks:
        last_b, first_b = _norm_dec_name(b.get("Deceased Owner", ""))
        if not last_b:
            continue
        tokens_b = _dec_name_tokens(b.get("Deceased Owner", ""))
        # Look up candidates using ANY of the tokens
        candidates = []
        for tok in (last_b, first_b):
            for r in named_by_key.get((b["County"], tok), []):
                if r not in candidates:
                    candidates.append(r)
        # Match strategies:
        #   1. Strict 2-token match (Last, First ↔ First Last orderings)
        #   2. Subset match (truncated newspaper name is a subset of the
        #      full eCourts name — catches 'Walker, Betty' ↔
        #      'Walker, Betty Louise')
        for r in candidates:
            last_r, first_r = _norm_dec_name(r.get("Deceased Owner", ""))
            tokens_r = _dec_name_tokens(r.get("Deceased Owner", ""))
            strict = (
                (last_b == last_r or last_b == first_r)
                and (first_b == first_r or first_b == last_r)
            )
            # Subset = blank name's tokens are all contained in named name's
            # tokens, AND there's at least 2 tokens of overlap (so single
            # 'WHITE' doesn't merge into 'WHITE, JANE DOE').
            subset = (
                tokens_b
                and tokens_b.issubset(tokens_r)
                and len(tokens_b & tokens_r) >= 2
            )
            if strict or subset:
                # Match found — merge
                for col in ("Mailing Address", "Mailing City", "Mailing State", "Mailing Zip",
                            "Property Address", "Property City", "Property Zip", "Property use",
                            "Parcel ID", "Beneficiaries", "Notes", "First Name", "Last Name",
                            "Personal Representative"):
                    if not (r.get(col) or "").strip() and (b.get(col) or "").strip():
                        r[col] = b[col]
                to_drop_ids.add(id(b))
                merged += 1
                break

    kept = [r for r in rows if id(r) not in to_drop_ids]
    remaining_blanks = sum(1 for r in kept if not (r.get("Case No.") or "").strip())
    return kept, merged, remaining_blanks


def fill_missing_pr_mailing_from_property(rows: list[dict]) -> int:
    """For rows where a Personal Rep / Executor / Interested Person is named
    but their mailing address was not in the court record, fall back to
    using the property address as the mailing. Direct mail still gets
    delivered (to the property), addressed to the PR by name.

    This matches the user's manual workflow. Phase 2 (future): replace
    with the PR's actual mailing or the heir's mailing once deep
    prospecting (obituary + skip trace) finds them.

    Returns the number of rows updated. Skips 'Heirs of' rows (their
    mailing was already set this way by the Heirs-of transform).
    """
    filled = 0
    for r in rows:
        if r.get("First Name") == "Heirs":
            continue
        if not (r.get("Personal Representative") or "").strip():
            continue  # no PR named — falls through to Heirs-of treatment elsewhere
        if (r.get("Mailing Address") or "").strip():
            continue  # already has a mailing
        prop_addr = (r.get("Property Address") or "").strip()
        if not prop_addr:
            continue  # no property to fall back to
        r["Mailing Address"] = prop_addr
        if (r.get("Property City") or "").strip():
            r["Mailing City"] = r["Property City"]
        r["Mailing State"] = "NC"
        if (r.get("Property Zip") or "").strip():
            r["Mailing Zip"] = r["Property Zip"]
        filled += 1
    return filled


def drop_executor_at_property(rows: list[dict]) -> tuple[list[dict], int]:
    """Drop rows where the executor's mailing address matches the property
    address — meaning the executor LIVES at the property. They almost
    certainly inherit and stay (heir-occupied — bad probate lead).

    Only applies to court-named-executor rows (NOT 'Heirs of ...' rows
    where we deliberately set mailing := property).
    """
    def norm_addr(s):
        return ''.join(c.lower() for c in (s or '') if c.isalnum())
    kept = []
    dropped = 0
    for r in rows:
        if r.get("First Name") == "Heirs":
            kept.append(r)
            continue
        prop = norm_addr(r.get("Property Address"))
        mail = norm_addr(r.get("Mailing Address"))
        if prop and mail and prop == mail:
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


def _parcel_use_tier(use: str) -> int:
    """Same residential-first tiering used by nc_ftm_writer.collapse_by_case."""
    u = (use or "").upper()
    if "COMMERCIAL" in u or "INDUSTRIAL" in u or "OFFICE" in u:
        return 0
    if "VACANT" in u or "LAND" in u:
        return 1
    if u in {"SFR", "RESIDENTIAL", "TOWNHOUSE", "CONDO", "MH",
             "MULTI-FAMILY", "DUPLEX"}:
        return 3
    return 2


def re_collapse_multi_parcel(rows: list[dict]) -> int:
    """For rows whose Notes contain 'PLUS N PARCELS' (multi-parcel decedents
    where the original scrape collapsed by market_value and may have
    picked a vacant lot or commercial parcel as main), re-fetch the
    decedent's parcels from GIS and pick the residential one as main.
    Updates the row in place and rewrites the PLUS-N-PARCELS note with
    the remaining parcels.

    Returns the number of rows whose main parcel was swapped.
    """
    from nc_gis_lookup import filter_for_lead_quality
    swapped = 0
    for r in rows:
        notes = (r.get("Notes") or "").strip()
        if "PLUS " not in notes.upper() or "PARCEL" not in notes.upper():
            continue
        current_use = (r.get("Property use") or "").strip()
        # Skip if main is already residential — no swap needed
        if _parcel_use_tier(current_use) == 3:
            continue
        dec = (r.get("Deceased Owner") or "").strip()
        county = (r.get("County") or "").strip()
        if not dec or not county or "IN THE MATTER" in dec.upper():
            continue
        try:
            results = lookup_properties(dec, county, min_score=0.7)
        except Exception:
            continue
        kept = filter_for_lead_quality(results)
        if len(kept) < 2:
            continue
        # Apply residential-first priority
        def sort_key(c):
            new_use = simplify_use_code(c.use_code, c.use_description, c.county) or ""
            return (_parcel_use_tier(new_use),
                    float(c.market_value or 0))
        sorted_kept = sorted(kept, key=sort_key, reverse=True)
        new_main = sorted_kept[0]
        new_use = simplify_use_code(new_main.use_code, new_main.use_description, new_main.county) or ""
        # Only swap if the new main is a higher tier than current
        if _parcel_use_tier(new_use) <= _parcel_use_tier(current_use):
            continue
        # Apply the new main's data
        street, city, zipc = _candidate_to_address_parts(new_main)
        r["Parcel ID"] = new_main.pid or ""
        r["Property Address"] = street
        r["Property City"] = city
        r["Property State"] = "NC"
        r["Property Zip"] = zipc
        r["Property use"] = new_use
        # Rebuild the PLUS-N-PARCELS note with the remaining parcels
        extras = sorted_kept[1:]
        if extras:
            lines = [f"PLUS {len(extras)} PARCEL{'S' if len(extras) > 1 else ''}"]
            for e in extras:
                bits = [e.pid or ""]
                es, ec, ez = _candidate_to_address_parts(e)
                addr = " ".join(filter(None, [es, ec, ez])).strip()
                if addr:
                    bits.append(addr)
                eu = simplify_use_code(e.use_code, e.use_description, e.county) or ""
                if eu:
                    bits.append(f"[{eu}]")
                lines.append("  " + " | ".join(bits))
            r["Notes"] = "\n".join(lines)
        else:
            r["Notes"] = ""
        print(f"  Re-collapsed {county}/{dec}: {current_use!r} -> {new_use!r}, "
              f"main now {street}, {city}")
        swapped += 1
    return swapped


def drop_commercial(rows: list[dict]) -> tuple[list[dict], int]:
    """Drop rows whose Property use is genuinely Commercial/Industrial/Office.

    Run AFTER repair_addresses (which re-fetches suspect Cabarrus 'I'
    codes back to SFR). What's left tagged Commercial after that is the
    real commercial — drop it from probate lead lists.
    """
    kept = [r for r in rows if (r.get("Property use") or "").strip().upper() not in _SUSPECT_USES]
    dropped = len(rows) - len(kept)
    return kept, dropped


def collapse_duplicate_decedents(rows: list[dict]) -> tuple[list[dict], int]:
    """For rows with blank Case No. that share (County, Deceased Owner),
    collapse to one row + a 'PLUS N PARCELS' note. Mirrors the case-based
    collapse done at scrape time but works on the FTM CSV by-decedent
    when case_no never got populated.
    """
    from collections import defaultdict
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    keep_individually: list[dict] = []
    for r in rows:
        if (r.get("Case No.") or "").strip():
            keep_individually.append(r)  # has case# — already collapsed by scrape
            continue
        key = (r.get("County", ""), (r.get("Deceased Owner") or "").strip().upper())
        if not key[1]:
            keep_individually.append(r)
            continue
        groups[key].append(r)
    collapsed = 0
    for key, items in groups.items():
        if len(items) == 1:
            keep_individually.append(items[0])
            continue
        # Pick main = first (already sorted by scrape order)
        main = items[0]
        extras = items[1:]
        # Build a PLUS N PARCELS note appended to existing Notes
        lines = [f"PLUS {len(extras)} PARCEL{'S' if len(extras) > 1 else ''}"]
        for e in extras:
            bits = []
            if (e.get("Parcel ID") or "").strip():
                bits.append(e["Parcel ID"])
            addr = " ".join(filter(None, [e.get("Property Address", ""),
                                          e.get("Property City", ""),
                                          e.get("Property Zip", "")])).strip()
            if addr:
                bits.append(addr)
            if (e.get("Property use") or "").strip():
                bits.append(f"[{e['Property use']}]")
            lines.append("  " + " | ".join(bits))
        extra_note = "\n".join(lines)
        existing_notes = (main.get("Notes") or "").strip()
        if existing_notes:
            main["Notes"] = existing_notes + "\n" + extra_note
        else:
            main["Notes"] = extra_note
        keep_individually.append(main)
        collapsed += len(extras)
    return keep_individually, collapsed


# Beneficiary name tokens that mean "not a person" — skip these as PR fallback.
_NON_PERSON_TOKENS = (
    "TRUST", "LLC", "CORP", "ESTATE OF", "INC", "FOUNDATION",
    "TRUSTEE", "FAMILY TRUST", "REVOCABLE", "IRREVOCABLE",
    "MINISTRIES", "CHURCH", "BAPTIST", "METHODIST", "CATHOLIC",
)


def _is_person_name(name: str) -> bool:
    """True when the beneficiary name looks like an individual (not a trust/LLC/etc)."""
    if not name:
        return False
    up = name.upper()
    if any(tok in up for tok in _NON_PERSON_TOKENS):
        return False
    return True


def _parse_beneficiary_line(line: str) -> dict | None:
    """Parse one Beneficiaries-cell line in our format:
        "Last, First Middle - street, city, NC zip"
    Returns dict with name/first/last/street/city/state/zip, or None on failure.
    """
    if " - " not in line:
        return None
    name_part, _, addr_part = line.partition(" - ")
    name_part = name_part.strip()
    addr_part = addr_part.strip()
    if not name_part or not _is_person_name(name_part):
        return None
    # Parse name: "Last, First Middle" preferred; fallback to space-separated
    first = middle = last = ""
    if "," in name_part:
        last_chunk, _, fm_chunk = name_part.partition(",")
        last = last_chunk.strip()
        fm_tokens = fm_chunk.strip().split()
        if fm_tokens:
            first = fm_tokens[0]
            middle = " ".join(fm_tokens[1:])
    else:
        tokens = name_part.split()
        if len(tokens) >= 2:
            first, last = tokens[0], tokens[-1]
            middle = " ".join(tokens[1:-1])
    if not first or not last:
        return None
    # Parse address: "street, city, NC zip"
    parts = [p.strip() for p in addr_part.split(",") if p.strip()]
    street = city = state = zipc = ""
    if len(parts) >= 1:
        street = parts[0]
    if len(parts) >= 2:
        city = parts[1]
    if len(parts) >= 3:
        # Last element: "NC 12345" or "NC 12345-6789"
        tail = parts[-1].strip().split()
        if tail:
            if len(tail[0]) == 2 and tail[0].isalpha():
                state = tail[0].upper()
            for t in tail:
                if t and (t[0].isdigit() or (len(t) >= 5 and t[:5].isdigit())):
                    zipc = t
                    break
    # Need at least street + (city OR zip) to be a usable mailing
    if not street or not (city or zipc):
        return None
    return {
        "name": name_part,
        "first": first,
        "middle": middle,
        "last": last,
        "street": street,
        "city": city,
        "state": state or "NC",
        "zip": zipc,
    }


def promote_beneficiary_to_pr(row: dict) -> dict | None:
    """For rows where no court-named executor exists, look at the Beneficiaries
    column for a person with a usable mailing address. If found, return the
    parsed beneficiary dict — the caller wires it into the Executor / Mailing
    fields. Returns None when no suitable beneficiary exists (caller falls
    back to generic 'Heirs of [Decedent]' treatment).
    """
    bens_raw = (row.get("Beneficiaries") or "").strip()
    if not bens_raw:
        return None
    # The CSV stores beneficiaries as newline-separated; the XLSX collapses
    # to ' | '. Handle both delimiters.
    if "\n" in bens_raw:
        lines = [ln.strip() for ln in bens_raw.split("\n") if ln.strip()]
    else:
        lines = [ln.strip() for ln in bens_raw.split(" | ") if ln.strip()]
    for ln in lines:
        parsed = _parse_beneficiary_line(ln)
        if parsed:
            return parsed
    return None


def _split_person_name(full: str) -> tuple[str, str]:
    """Split a 'First Middle Last' string into (first, last). Best-effort."""
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def promote_dm_to_pr(row: dict) -> dict | None:
    """If DM Name is populated (obituary enricher found a verified-living
    heir) and the row has no court PR, promote the DM to PR contact.

    Prefers the DM's mailing address if available; otherwise falls back to
    property address so direct mail still reaches the lead.

    Returns dict with promoted fields or None if no usable DM.
    """
    dm_name = (row.get("DM Name") or "").strip()
    if not dm_name:
        return None
    # Skip degenerate placeholders — let the row fall through to the
    # regular "Heirs of [Decedent]" path instead:
    #   - "Heirs of ..." (already a generic placeholder)
    #   - "Estate of ..." (obituary enricher's Path 5 estate-fallback —
    #     fires when no survivors are named in the obituary)
    #   - Pure relationship words like "Wife"/"Husband" (parser pulled
    #     the relation label instead of the actual person's name)
    dm_lower = dm_name.lower()
    if dm_lower.startswith("heirs of") or dm_lower.startswith("estate of"):
        return None
    if dm_lower in {"wife", "husband", "spouse", "son", "daughter",
                    "brother", "sister", "mother", "father", "child",
                    "children", "family"}:
        return None
    first, last = _split_person_name(dm_name)
    return {
        "name": dm_name,
        "first": first,
        "last": last,
        "relationship": (row.get("DM Relationship") or "").strip(),
    }


def prep_for_datasift(rows: list[dict]) -> tuple[list[dict], int, int, int, int]:
    """For rows with a parcel + no court-named executor:
      1. If an obituary-verified DM exists (DM Name populated by the
         enricher), promote the DM to PR contact — real person, court-
         independent confirmation.
      2. Otherwise, try to promote a usable BENEFICIARY (person, not
         trust/LLC, with a mailing address) — far better than a generic
         'Heirs of [Decedent]' mailer.
      3. If neither exists, fall back to 'Heirs of [Decedent]' with the
         property as mailing address.

    Returns (kept_rows, dropped_no_parcel, dm_promoted, beneficiary_promoted, generic_heirs).
    """
    kept = [r for r in rows if (r.get("Parcel ID") or "").strip()]
    dropped = len(rows) - len(kept)
    dm_promoted = 0
    promoted = 0
    heirs = 0
    for r in kept:
        if (r.get("Personal Representative") or "").strip():
            continue
        decedent = (r.get("Deceased Owner") or "").strip()
        if not decedent or "IN THE MATTER" in decedent.upper():
            continue

        # Try DM promotion first (obituary-verified living heir)
        dm = promote_dm_to_pr(r)
        if dm:
            r["Personal Representative"] = dm["name"]
            r["First Name"] = dm["first"]
            r["Last Name"] = dm["last"]
            # DM mailing address isn't preserved through the polish CSV
            # round-trip — fall back to property address so direct mail
            # still reaches the property (lead can be skip-traced in
            # DataSift post-upload).
            if (r.get("Property Address") or "").strip():
                r["Mailing Address"] = r["Property Address"]
            if (r.get("Property City") or "").strip():
                r["Mailing City"] = r["Property City"]
            r["Mailing State"] = "NC"
            if (r.get("Property Zip") or "").strip():
                r["Mailing Zip"] = r["Property Zip"]
            dm_promoted += 1
            continue

        # Then beneficiary promotion
        ben = promote_beneficiary_to_pr(r)
        if ben:
            # Build a nice "Last, First Middle" display name preserving original casing
            r["Personal Representative"] = ben["name"]
            r["First Name"] = ben["first"]
            r["Last Name"] = ben["last"]
            r["Mailing Address"] = ben["street"]
            r["Mailing City"] = ben["city"]
            r["Mailing State"] = ben["state"]
            r["Mailing Zip"] = ben["zip"]
            promoted += 1
            continue

        # Fall back to generic Heirs-of with property as mailing
        _f, _m, last = split_decedent_name(decedent)
        r["Personal Representative"] = f"Heirs of {decedent}"
        r["First Name"] = "Heirs"
        r["Last Name"] = last.title() if last.isupper() else last
        if (r.get("Property Address") or "").strip():
            r["Mailing Address"] = r["Property Address"]
        if (r.get("Property City") or "").strip():
            r["Mailing City"] = r["Property City"]
        r["Mailing State"] = "NC"
        if (r.get("Property Zip") or "").strip():
            r["Mailing Zip"] = r["Property Zip"]
        heirs += 1
    return kept, dropped, dm_promoted, promoted, heirs


def run(src_path: Path, tag: str, ts: str) -> None:
    print(f"\n=== {tag.upper()}: {src_path.name} ===")
    with src_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # Back-compat: pre-rename CSVs used "Executor Full Name". Normalize to
    # the current "Personal Representative" so downstream logic only sees
    # one column name. Idempotent — no-op when column is already renamed.
    for r in rows:
        if "Executor Full Name" in r and "Personal Representative" not in r:
            r["Personal Representative"] = r.pop("Executor Full Name")
    print(f"Loaded {len(rows)} rows")

    print("Step -1: backfill blank Case No. from user's manual XLSX archive")
    n_archive_hit, n_archive_miss = backfill_from_manual_archive(rows)
    print(f"  Archive-backfilled: {n_archive_hit}  No-match (still blank-case): {n_archive_miss}")

    print("Step -0.8: drop archive duplicates (already in prior-week manual pipeline)")
    rows, n_dropped_archive = drop_archive_duplicates(rows)
    print(f"  Dropped archive-duplicate rows: {n_dropped_archive}  Remaining: {len(rows)}")

    print("Step -0.5: soft-dedup blank-case-no rows against same-decedent named rows in this week")
    rows, n_merged, n_still_blank = soft_dedup_blank_case_no(rows)
    print(f"  Merged dupes: {n_merged}  Remaining blank-case-no: {n_still_blank}")

    print("Step 0: validate existing parcel matches against new middle-name-aware matcher")
    n_blanked, audit_rejected_pids = validate_existing_matches(rows)
    print(f"  Blanked false-positive matches: {n_blanked}  "
          f"(rejected PIDs blacklisted from re-search: {len(audit_rejected_pids)})")

    print("Step 0.5: re-search for correct parcel where audit blanked a wrong match")
    n_refound = research_blank_parcels(rows, audit_rejected_pids=audit_rejected_pids)
    print(f"  Re-found correct parcels: {n_refound}")

    print("Step 1: repair property addresses + re-classify suspect Commercial rows")
    n_repaired = repair_addresses(rows)
    print(f"  Repaired: {n_repaired}")

    print("Step 1.5: re-collapse multi-parcel decedents (prefer residential as main)")
    n_swapped = re_collapse_multi_parcel(rows)
    print(f"  Swapped vacant/commercial-main -> residential-main: {n_swapped}")

    print("Step 1.7: backfill Property Value from GIS where missing")
    n_priced = populate_property_values(rows)
    print(f"  Filled Property Value: {n_priced}")

    print("Step 1.8: drop properties valued over $500K (user's buy-box cap)")
    rows, n_over_500k = drop_over_500k(rows, cap=500_000)
    print(f"  Dropped >$500K: {n_over_500k}  Remaining: {len(rows)}")

    print("Step 1.9: drop heir-occupied (executor mailing == property address)")
    rows, n_heir_occupied = drop_executor_at_property(rows)
    print(f"  Dropped heir-occupied: {n_heir_occupied}  Remaining: {len(rows)}")

    print("Step 1.95: fill missing PR mailing from property (so direct mail still goes out)")
    n_filled_pr = fill_missing_pr_mailing_from_property(rows)
    print(f"  PR mailing fallback applied: {n_filled_pr}")

    print("Step 2: drop genuinely commercial rows")
    rows, n_commercial = drop_commercial(rows)
    print(f"  Dropped commercial: {n_commercial}  Remaining: {len(rows)}")

    print("Step 3: collapse duplicate decedent rows (blank Case No.)")
    rows, n_collapsed = collapse_duplicate_decedents(rows)
    print(f"  Collapsed: {n_collapsed} parcels into PLUS-N-PARCELS notes  Remaining: {len(rows)}")

    print("Step 3.5: clean bad-city / bad-zip leftovers (suffix/state/numeric noise)")
    n_clean_city, n_clean_zip = clean_bad_city_zip_in_place(rows)
    print(f"  Cleaned cities: {n_clean_city}  Reformatted/cleared zips: {n_clean_zip}")

    print("Step 4: filter to has-parcel; promote DM/beneficiary or apply 'Heirs of' fallback")
    kept, dropped, dm_promoted, promoted, heirs = prep_for_datasift(rows)
    print(f"  Rows in: {len(rows)}  Dropped (no parcel): {dropped}  "
          f"DM-promoted: {dm_promoted}  Beneficiary-promoted: {promoted}  "
          f"Generic Heirs-of: {heirs}  Out: {len(kept)}")

    out_csv = Path("output") / f"nc_estates_ftm_{ts}_{tag}_datasift.csv"
    out_xlsx = Path("output") / f"nc_estates_ftm_{ts}_{tag}_datasift.xlsx"
    write_csv(kept, out_csv)
    write_xlsx(kept, out_xlsx)
    print(f"  Wrote: {out_csv}")
    print(f"  Wrote: {out_xlsx}")


def main() -> None:
    """Process every week that has a merged file. Auto-picks the latest
    *_weekN_merged.csv per ISO week — week-agnostic so new weeks (22, 23,
    ...) are handled without code changes.
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Discover every week with a merged file; keep the most recent file per
    # week. glob() sorted ascending puts older timestamps first, so the last
    # assignment per week wins (newest scrape).
    by_week: dict[int, Path] = {}
    for fp in sorted(Path("output").glob("nc_estates_ftm_*_week*_merged.csv")):
        m = re.search(r"_week(\d+)_merged\.csv$", fp.name)
        if not m:
            continue
        by_week[int(m.group(1))] = fp

    if not by_week:
        print("No *_weekN_merged.csv files in output/. Run prepare_weekly_input.py first.")
        return

    for wk in sorted(by_week):
        print(f"\n{'=' * 70}")
        print(f"=== Week {wk}: {by_week[wk].name} ===")
        print(f"{'=' * 70}")
        run(by_week[wk], f"week{wk}", ts)


if __name__ == "__main__":
    main()
