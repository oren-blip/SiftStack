"""Smoke test the Mecklenburg polaris3g name search + pipeline expansion."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nc_gis_lookup import (  # noqa: E402
    lookup_properties,
    filter_for_lead_quality,
    expand_notices_with_gis,
)
from notice_parser import NoticeData  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 1. Raw lookup test with common names — should hit Mecklenburg residents
    raw_cases = [
        ("Mecklenburg", "John Smith"),
        ("Mecklenburg", "Mary Johnson"),
        ("Mecklenburg", "Robert Williams"),
    ]
    for county, name in raw_cases:
        print(f"\n=== {county} :: {name!r} ===")
        candidates = lookup_properties(name, county)
        print(f"  {len(candidates)} candidates passed scoring")
        for c in candidates[:5]:
            print(f"  [{c.match_score:.2f}] pid={c.pid} {c.use_code}")
            print(f"        owner:   {c.owner_name}")
            print(f"        situs:   {c.situs_address}")
            print(f"        mailing: {c.mailing_address}")
            print(f"        offsite={c.owner_offsite} land={c.is_vacant_land}")
        kept = filter_for_lead_quality(candidates)
        print(f"  -> {len(kept)} keep after heir-occupancy filter")

    # 2. Pipeline expansion test — simulate a probate notice with a decedent
    #    name + Mecklenburg county
    print("\n=== Pipeline expansion test ===")
    fake_notices = [
        NoticeData(
            county="Mecklenburg",
            state="NC",
            notice_type="probate",
            date_added="2026-05-15",
            decedent_name="Beaulah Goings",
            source_url="https://example.com/case=26E001234-590",
            raw_text="IN THE MATTER OF THE ESTATE OF Beaulah Goings",
        ),
        NoticeData(
            county="Mecklenburg",
            state="NC",
            notice_type="probate",
            date_added="2026-05-15",
            decedent_name="Brenda Bell",
            source_url="https://example.com/case=26E001235-590",
            raw_text="IN THE MATTER OF THE ESTATE OF Brenda Bell",
        ),
    ]
    out, stats = expand_notices_with_gis(fake_notices)
    print(f"  stats: {stats}")
    for n in out:
        print(f"  -> {n.decedent_name} | {n.address}, {n.city} NC {n.zip} | pid={n.parcel_id} | val=${n.estimated_value}")
        if n.owner_street:
            print(f"     mailing: {n.owner_street}, {n.owner_city} {n.owner_state} {n.owner_zip}")


if __name__ == "__main__":
    main()
