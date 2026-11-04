"""Availability Time and As-of: the single place that interprets time.

Availability Time is the moment a Filing became public: its EDGAR acceptance
datetime (ADR-0001). An As-of is the point in time a question is asked from;
only Filings and Facts with Availability Time <= As-of may be used.

Every other module calls ``normalize_as_of`` instead of parsing As-of input
itself, and compares timezone-aware US Eastern datetimes.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

_END_OF_DAY = time(23, 59, 59, 999999)


def parse_acceptance(value: str | None) -> datetime | None:
    """Parse the submissions API's ``acceptanceDateTime`` into US Eastern time.

    The API's trailing ``Z`` is genuine UTC: AAPL's 8-K 0000320193-26-000024
    reads ``2026-11-02T21:30:23.000Z`` while its EDGAR index page shows
    "Accepted 2026-11-02 16:30:23" (EST), and 0000320193-26-000018 reads
    ``2026-07-30T20:30:28.000Z`` against 16:30:28 (EDT).
    """
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"acceptanceDateTime without a timezone: {value!r}")
    return parsed.astimezone(EASTERN)


def normalize_as_of(value: datetime | date | str | None = None) -> datetime:
    """Turn any As-of input into a timezone-aware US Eastern datetime.

    - ``None`` means now.
    - A date (or ``YYYY-MM-DD`` string) means the end of that day, Eastern.
    - A naive datetime is taken to be Eastern; an aware one is converted.
    """
    if value is None:
        return datetime.now(EASTERN)
    if isinstance(value, str):
        text = value.strip()
        if len(text) == 10:
            value = date.fromisoformat(text)
        else:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=EASTERN)
        return value.astimezone(EASTERN)
    if isinstance(value, date):
        return datetime.combine(value, _END_OF_DAY, tzinfo=EASTERN)
    raise TypeError(f"Unsupported As-of value: {value!r}")


def is_available(availability_time: datetime | None, as_of: datetime) -> bool:
    """True if something with this Availability Time may be used at ``as_of``.

    Unknown Availability Time is never available.
    """
    return availability_time is not None and availability_time <= as_of
