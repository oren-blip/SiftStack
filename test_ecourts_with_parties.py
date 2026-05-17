"""Test the eCourts scraper with the new Parties enrichment.

Pulls last 14 days of Mecklenburg probate cases, then prints executor +
beneficiary data for each — should mirror the user's FTM manual format.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ecourts_scraper import scrape_ecourts  # noqa: E402


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    notices = await scrape_ecourts(
        counties=["Mecklenburg"],
        types=["probate"],
        since_date_override="2026-05-03",
        max_records=10,
        headless=True,
    )

    print(f"\n=== {len(notices)} probate cases ===\n")
    for n in notices:
        print(f"Case: {n.case_number}")
        print(f"  Decedent: {n.decedent_name}")
        print(f"  Executor: {n.executor_first_name} {n.executor_last_name}")
        print(f"  Exec addr: {n.owner_street}, {n.owner_city}, {n.owner_state} {n.owner_zip}")
        if n.beneficiaries_json:
            bens = json.loads(n.beneficiaries_json)
            print(f"  Beneficiaries ({len(bens)}):")
            for b in bens:
                print(f"    - {b['name']}: {b['street']}, {b['city']}, {b['state']} {b['zip']}")
        else:
            print(f"  Beneficiaries: (none on file)")
        print()


if __name__ == "__main__":
    asyncio.run(main())
