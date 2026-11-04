"""Agent tools: filing_search, get_financials, section_diff. Every tool takes as_of."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.filings.availability import normalize_as_of
from src.filings.diff import diff_paragraphs, section_paragraphs
from src.filings.edgar import ROOT, EdgarClient, EdgarDownloader
from src.filings.xbrl import fiscal_year, get_fact
from src.rag.index import CHUNKS_DB
from src.rag.retrieve import search

FACTS_DB = Path(os.getenv("FACTS_DB", ROOT / "data" / "facts.db"))


def filing_search(query: str, ticker: str | None = None, form: str | None = None,
                  fiscal_year: int | None = None, section: str | None = None,
                  as_of: datetime | date | str | None = None, *,
                  accession_no: str | None = None, latest: bool = False,
                  downloader: EdgarDownloader | None = None,
                  db_path: Path = CHUNKS_DB) -> list[dict[str, Any]]:
    """Top 5 Chunks for ``query`` from Filings available at ``as_of``.

    ``form`` matches exactly (``10-K`` excludes ``10-K/A``). ``latest=True``
    (with ``ticker`` and ``form``) searches only the latest such Filing at
    ``as_of``, e.g. "the latest 10-K" means the latest Original.

    Each result carries its text, score and citation fields: Ticker, form,
    Fiscal Year, Fiscal Period, Section, accession number, Availability Time and URL.
    """
    cik = None
    if ticker is not None:
        downloader = downloader or EdgarDownloader(EdgarClient())
        cik, _ = downloader.lookup(ticker)
    return search(db_path, query, normalize_as_of(as_of), cik=cik, form=form,
                  fiscal_year=fiscal_year, section=section, accession_no=accession_no,
                  latest=latest)


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


def section_diff(ticker: str, section: str, form: str, fiscal_year_a: int, fiscal_year_b: int,
                 as_of: datetime | date | str | None = None, *,
                 downloader: EdgarDownloader | None = None) -> dict[str, Any]:
    """What changed in ``section`` from the ``fiscal_year_a`` Filing of ``form``
    to the ``fiscal_year_b`` one, using only Filings available at ``as_of``.

    Each Fiscal Year resolves to the Original Filing of ``form``; pass an
    Amendment form (``10-K/A``) to compare Amendments. Returns a similarity
    score, added and removed paragraphs, and both Filings' Citation fields.
    Raises ValueError if a Filing is missing, not yet public, or lacks the Section.
    """
    downloader = downloader or EdgarDownloader(EdgarClient())
    cik, _ = downloader.lookup(ticker)
    as_of = normalize_as_of(as_of)
    sub_path = downloader.cache_dir / "submissions" / f"CIK{cik:010d}.json"
    fye = json.loads(sub_path.read_text(encoding="utf-8"))["fiscalYearEnd"]
    saved = [(p.parent, json.loads(p.read_text(encoding="utf-8")))
             for p in (downloader.filings_dir / str(cik)).glob("*/metadata.json")]

    sides = []
    for fy in (fiscal_year_a, fiscal_year_b):
        matches = [(folder, m) for folder, m in saved if m["form"] == form
                   and fiscal_year(date.fromisoformat(m["report_date"]), fye) == fy]
        if len(matches) != 1:
            raise ValueError(f"Expected one {form} for {ticker} FY{fy}, found {len(matches)}")
        folder, meta = matches[0]
        available = datetime.fromisoformat(meta["availability_time"])
        if available > as_of:
            raise ValueError(f"{ticker} {form} FY{fy} ({meta['accession_no']}) was not public "
                             f"until {available.isoformat()}, after As-of {as_of.isoformat()}")
        paragraphs = section_paragraphs(folder, meta["primary_document"], form, section)
        if paragraphs is None:
            raise ValueError(f"{ticker} {form} FY{fy} ({meta['accession_no']}) has no {section}")
        citation = {"ticker": meta["ticker"], "form": meta["form"], "fiscal_year": fy,
                    "section": section, "accession_no": meta["accession_no"],
                    "availability_time": available, "url": meta["url"]}
        sides.append((paragraphs, citation))

    (a, citation_a), (b, citation_b) = sides
    return diff_paragraphs(a, b) | {"citation_a": citation_a, "citation_b": citation_b}
