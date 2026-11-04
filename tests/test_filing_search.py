"""10-K Sections through filing_search (BM25) on the fixture Universe."""

from __future__ import annotations

import sqlite3

import pytest

from src.agents.tools import filing_search
from src.rag import index
from tests import fixture_universe as fu


@pytest.fixture
def db(universe, tmp_path):
    path = tmp_path / "chunks.db"
    index.index_company(universe.downloader, fu.TICKER, path)
    return path


def _search(universe, db, query, **kw):
    return filing_search(query, ticker=fu.TICKER, downloader=universe.downloader, db_path=db, **kw)


def test_10k_not_yet_public_is_never_returned(universe, db):
    assert _search(universe, db, "export restrictions", as_of="2024-02-19") == []

    [hit, *_] = _search(universe, db, "export restrictions", as_of="2024-02-20")
    assert (hit["accession_no"], hit["section"], hit["fiscal_year"]) == (fu.ACC_10K_2023, "Item 1A", 2023)
    assert hit["availability_time"] == fu.AVAILABILITY[fu.ACC_10K_2023]
    assert (hit["ticker"], hit["form"], hit["is_amendment"]) == (fu.TICKER, "10-K", False)
    assert hit["url"].endswith(fu.DOCS[fu.ACC_10K_2023])
    assert "export restrictions" in hit["text"]


def test_table_comes_back_whole_with_caption_across_chunk_boundary(universe, tmp_path, monkeypatch):
    monkeypatch.setattr(index, "CHUNK_WORDS", 10)
    monkeypatch.setattr(index, "OVERLAP_WORDS", 2)
    db = tmp_path / "small.db"
    index.index_company(universe.downloader, fu.TICKER, db)

    hits = _search(universe, db, "revenue by segment sensors services", section="Item 7",
                   fiscal_year=2023, as_of=None)
    [table] = [h for h in hits if h["is_table"]]
    assert table["text"].startswith("Table 1: Revenue by segment (in millions)")
    assert "| Total | 1200 | 1000 |" in table["text"]
    assert all(len(h["text"].split()) <= 10 for h in hits if not h["is_table"])


def test_table_of_contents_is_skipped(universe, db):
    assert _search(universe, db, "contents", as_of=None) == []
    with sqlite3.connect(db) as conn:
        texts = [t for (t,) in conn.execute("SELECT text FROM chunks")]
    assert not any("| 22 |" in t for t in texts)  # TOC page numbers


def test_section_filter_limits_results(universe, db):
    hits = _search(universe, db, "foreign currency exchange", section="Item 7A", as_of=None)
    assert hits and {h["section"] for h in hits} == {"Item 7A"}


def test_only_10k_sections_are_indexed(universe, db):
    with sqlite3.connect(db) as conn:
        sections = {s for (s,) in conn.execute("SELECT DISTINCT section FROM chunks")}
        forms = {f for (f,) in conn.execute("SELECT DISTINCT form FROM chunks")}
    assert sections == {"Item 1", "Item 1A", "Item 7", "Item 7A", "Item 8", "Item 9A"}
    assert forms == {"10-K"}


def test_reindexing_replaces_chunks(universe, db):
    first = index.index_company(universe.downloader, fu.TICKER, db)
    second = index.index_company(universe.downloader, fu.TICKER, db)
    with sqlite3.connect(db) as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    assert first == second
    assert total == sum(second.values())


def test_filing_without_sections_is_skipped_with_warning(universe, tmp_path, capsys):
    folder = universe.downloader.filings_dir / str(fu.CIK) / fu.ACC_10K_2022
    (folder / fu.DOCS[fu.ACC_10K_2022]).write_bytes(b"<html><body><p>No items here.</p></body></html>")

    counts = index.index_company(universe.downloader, fu.TICKER, tmp_path / "chunks.db")
    assert counts[fu.ACC_10K_2022] == 0
    assert f"{fu.ACC_10K_2022}: no Sections found" in capsys.readouterr().out
