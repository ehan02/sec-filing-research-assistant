"""Load XBRL companyfacts into the SQLite facts table; point-in-time get_fact().

Fiscal Year and Fiscal Period describe the period a value covers, derived
from its own dates and the Company's fiscal year end, never copied from the
raw XBRL ``fy``/``fp`` fields (ADR-0002). Each Fact's Availability Time is
that of the Filing named by its accession number (ADR-0001).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.filings.availability import EASTERN
from src.filings.edgar import EdgarDownloader

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    cik INTEGER NOT NULL,
    concept TEXT NOT NULL,
    unit TEXT NOT NULL,
    value REAL NOT NULL,
    period_start TEXT,
    period_end TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_period TEXT NOT NULL,
    form TEXT,
    accn TEXT NOT NULL,
    availability_time TEXT NOT NULL,  -- UTC ISO, so text order is time order
    UNIQUE (cik, concept, unit, period_start, period_end, accn)
);
CREATE INDEX IF NOT EXISTS facts_lookup
    ON facts (cik, concept, fiscal_year, fiscal_period, availability_time);
"""

# A 52/53-week fiscal year can end a few days either side of its nominal date.
_FYE_SLACK = timedelta(days=7)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def fiscal_year(end: date, fiscal_year_end: str) -> int:
    """Fiscal Year a period ending on ``end`` falls in, named by the calendar
    year in which that fiscal year ends. ``fiscal_year_end`` is EDGAR's MMDD."""
    month, day = int(fiscal_year_end[:2]), int(fiscal_year_end[2:])
    for year in (end.year - 1, end.year, end.year + 1):
        if end <= date(year, month, day) + _FYE_SLACK:
            return year
    raise AssertionError("unreachable")


def fiscal_period(start: date | None, end: date, fy: int, fiscal_year_end: str) -> str | None:
    """``FY`` or ``Q1``–``Q4``; None for durations that are neither a quarter
    nor a year (year-to-date values in 10-Qs)."""
    if start is not None:
        days = (end - start).days
        if 350 <= days <= 380:
            return "FY"
        if not 80 <= days <= 100:
            return None
    year_end = date(fy, int(fiscal_year_end[:2]), int(fiscal_year_end[2:]))
    quarters_before_year_end = round((year_end - end).days / 91.3)
    if start is None and quarters_before_year_end == 0:
        return "FY"
    return f"Q{4 - quarters_before_year_end}"


def load_facts(downloader: EdgarDownloader, ticker: str, db_path: Path) -> dict[str, int]:
    """Replace a Company's rows in the facts table from its cached companyfacts.

    Returns a load report: Facts loaded, skipped because their accession
    number has no known Availability Time, and skipped because their
    duration is neither a quarter nor a year.
    """
    cik, _ = downloader.lookup(ticker)
    facts_path = downloader.download_companyfacts(ticker)
    times = downloader.availability_times(ticker)
    sub_path = downloader.cache_dir / "submissions" / f"CIK{cik:010d}.json"
    fye = json.loads(sub_path.read_text(encoding="utf-8"))["fiscalYearEnd"]

    report = {"loaded": 0, "unknown_accession": 0, "other_duration": 0}
    rows = []
    companyfacts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path else {}
    for taxonomy, concepts in companyfacts.get("facts", {}).items():
        for name, concept in concepts.items():
            for unit, values in concept["units"].items():
                for v in values:
                    available = times.get(v["accn"])
                    if available is None:
                        report["unknown_accession"] += 1
                        continue
                    start = date.fromisoformat(v["start"]) if "start" in v else None
                    end = date.fromisoformat(v["end"])
                    fy = fiscal_year(end, fye)
                    fp = fiscal_period(start, end, fy, fye)
                    if fp is None:
                        report["other_duration"] += 1
                        continue
                    rows.append((cik, f"{taxonomy}:{name}", unit, v["val"],
                                 v.get("start"), v["end"], fy, fp, v.get("form"), v["accn"],
                                 available.astimezone(timezone.utc).isoformat()))

    with connect(db_path) as conn:
        conn.execute("DELETE FROM facts WHERE cik = ?", (cik,))
        conn.executemany("INSERT OR IGNORE INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    report["loaded"] = len(rows)
    return report


def get_fact(db_path: Path, cik: int, concept: str, fy: int, fp: str,
             as_of: datetime) -> dict[str, Any] | None:
    """The value for a Fiscal Year/Period with the latest Availability Time at
    or before ``as_of``, with the accession number that reported it."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM facts WHERE cik = ? AND concept = ? AND fiscal_year = ?"
            " AND fiscal_period = ? AND availability_time <= ?"
            " ORDER BY availability_time DESC LIMIT 1",
            (cik, concept, fy, fp, as_of.astimezone(timezone.utc).isoformat()),
        ).fetchone()
    return _to_dict(row) if row else None


def fact_history(db_path: Path, cik: int, concept: str, fy: int, fp: str) -> list[dict[str, Any]]:
    """Each distinct value reported for a period, in the order it became public.

    Repeats of the same value (comparatives) are dropped, so more than one
    entry means the value was restated.
    """
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM facts WHERE cik = ? AND concept = ? AND fiscal_year = ?"
            " AND fiscal_period = ? ORDER BY availability_time",
            (cik, concept, fy, fp),
        ).fetchall()
    history: list[dict[str, Any]] = []
    for row in rows:
        if not history or history[-1]["value"] != row["value"]:
            history.append(_to_dict(row))
    return history


def _to_dict(row: sqlite3.Row) -> dict[str, Any]:
    fact = dict(row)
    fact["availability_time"] = datetime.fromisoformat(fact["availability_time"]).astimezone(EASTERN)
    return fact
