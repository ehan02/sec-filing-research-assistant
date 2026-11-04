"""Agent tools: filing_search, get_financials, section_diff. Every tool takes as_of."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.filings.availability import normalize_as_of
from src.filings.edgar import ROOT, EdgarClient, EdgarDownloader
from src.filings.xbrl import get_fact
from src.rag.index import CHUNKS_DB
from src.rag.retrieve import search

FACTS_DB = Path(os.getenv("FACTS_DB", ROOT / "data" / "facts.db"))


def filing_search(query: str, ticker: str | None = None, form: str | None = None,
                  fiscal_year: int | None = None, section: str | None = None,
                  as_of: datetime | date | str | None = None, *,
                  downloader: EdgarDownloader | None = None,
                  db_path: Path = CHUNKS_DB) -> list[dict[str, Any]]:
    """Top 5 Chunks for ``query`` from Filings available at ``as_of``.

    Each result carries its text, score and citation fields: Ticker, form,
    Fiscal Year, Section, accession number, Availability Time and URL.
    """
    cik = None
    if ticker is not None:
        downloader = downloader or EdgarDownloader(EdgarClient())
        cik, _ = downloader.lookup(ticker)
    return search(db_path, query, normalize_as_of(as_of), cik=cik, form=form,
                  fiscal_year=fiscal_year, section=section)


def get_financials(ticker: str, concepts: list[str], periods: list[str],
                   as_of: datetime | date | str | None = None, *,
                   downloader: EdgarDownloader | None = None,
                   db_path: Path = FACTS_DB) -> list[dict[str, Any]]:
    """Values of XBRL ``concepts`` (e.g. ``us-gaap:Revenues``) for ``periods``
    (``FY2023`` or ``FY2024 Q1``) as they were known at ``as_of``.

    One row per concept and period, with the accession number and
    Availability Time of the Filing that reported the value. A value not yet
    public at ``as_of`` comes back as None.
    """
    downloader = downloader or EdgarDownloader(EdgarClient())
    cik, _ = downloader.lookup(ticker)
    as_of = normalize_as_of(as_of)
    table = []
    for period in periods:
        year, _, quarter = period.partition(" ")
        fy, fp = int(year.removeprefix("FY")), quarter or "FY"
        for concept in concepts:
            fact = get_fact(db_path, cik, concept, fy, fp, as_of)
            table.append({
                "concept": concept,
                "period": period,
                "value": fact["value"] if fact else None,
                "unit": fact["unit"] if fact else None,
                "accession_no": fact["accn"] if fact else None,
                "availability_time": fact["availability_time"] if fact else None,
            })
    return table
