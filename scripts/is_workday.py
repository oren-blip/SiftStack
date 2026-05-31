"""NC court workday gate.

Exit code:
  0  → today is a regular court day (Mon-Fri, not a holiday) — pipeline runs
  1  → today is a weekend or observed NC court holiday — pipeline should skip

Holiday list per Oren (matches NC General Court of Justice closure calendar):
  - New Year's Day                          (Jan 1)
  - Martin Luther King Jr. Day              (3rd Monday of January)
  - Good Friday                             (Friday before Easter Sunday)
  - Memorial Day                            (last Monday of May)
  - Independence Day                        (Jul 4)
  - Labor Day                               (1st Monday of September)
  - Veterans Day                            (Nov 11)
  - Thanksgiving + Friday after             (4th Thursday of November + day after)
  - Christmas block                         (Dec 24, 25, 26)

Federal "observed" shifts (when Jan 1 / Jul 4 / Nov 11 fall on Sat → Fri;
Sun → Mon) are not applied here intentionally — courts may observe
differently than federal employees, and skipping the actual date keeps
the rule simple to audit. If we ever need observed-day handling, add it
with explicit user confirmation.

Usage from a .bat:
    "%PY%" scripts\\is_workday.py
    if errorlevel 1 ( exit /b 0 )
    REM ... continue pipeline ...
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Return the date of the Nth weekday of the given month.

    weekday: 0=Mon, 1=Tue, ... 6=Sun
    n: 1 = first, 2 = second, etc.
    """
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the date of the last weekday in the given month."""
    # Walk back from the last day of the month
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    back = (last.weekday() - weekday) % 7
    return last - timedelta(days=back)


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm — Meeus/Jones/Butcher form."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nc_court_holidays(year: int) -> set[date]:
    return {
        date(year, 1, 1),                                  # New Year's Day
        _nth_weekday_of_month(year, 1, 0, 3),              # MLK Day = 3rd Mon Jan
        _easter_sunday(year) - timedelta(days=2),          # Good Friday
        _last_weekday_of_month(year, 5, 0),                # Memorial Day = last Mon May
        date(year, 7, 4),                                  # Independence Day
        _nth_weekday_of_month(year, 9, 0, 1),              # Labor Day = 1st Mon Sep
        date(year, 11, 11),                                # Veterans Day
        _nth_weekday_of_month(year, 11, 3, 4),             # Thanksgiving = 4th Thu Nov
        _nth_weekday_of_month(year, 11, 3, 4) + timedelta(days=1),  # Day after Thanksgiving
        date(year, 12, 24),                                # Christmas Eve
        date(year, 12, 25),                                # Christmas Day
        date(year, 12, 26),                                # Day after Christmas
    }


def is_workday(d: date) -> tuple[bool, str]:
    """Return (workday?, reason). Reason is a short human-readable label."""
    if d.weekday() == 5:
        return False, "Saturday"
    if d.weekday() == 6:
        return False, "Sunday"
    holidays = nc_court_holidays(d.year)
    if d in holidays:
        # Find which holiday this matches for a friendlier message
        names = {
            date(d.year, 1, 1): "New Year's Day",
            _nth_weekday_of_month(d.year, 1, 0, 3): "Martin Luther King Jr. Day",
            _easter_sunday(d.year) - timedelta(days=2): "Good Friday",
            _last_weekday_of_month(d.year, 5, 0): "Memorial Day",
            date(d.year, 7, 4): "Independence Day",
            _nth_weekday_of_month(d.year, 9, 0, 1): "Labor Day",
            date(d.year, 11, 11): "Veterans Day",
            _nth_weekday_of_month(d.year, 11, 3, 4): "Thanksgiving Day",
            _nth_weekday_of_month(d.year, 11, 3, 4) + timedelta(days=1): "Day after Thanksgiving",
            date(d.year, 12, 24): "Christmas Eve",
            date(d.year, 12, 25): "Christmas Day",
            date(d.year, 12, 26): "Day after Christmas",
        }
        return False, names.get(d, "NC court holiday")
    return True, "workday"


def main() -> int:
    # Optional --check <YYYY-MM-DD> for testing
    if len(sys.argv) >= 3 and sys.argv[1] == "--check":
        try:
            d = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
        except ValueError:
            print(f"bad date: {sys.argv[2]} (use YYYY-MM-DD)", file=sys.stderr)
            return 2
    else:
        d = date.today()
    ok, reason = is_workday(d)
    print(f"{d.isoformat()}: {'workday' if ok else 'SKIP'} ({reason})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
