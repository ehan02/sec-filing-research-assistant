"""10-K Sections through filing_search (BM25) on the fixture Universe."""

from __future__ import annotations

import sqlite3

import pytest

from src.agents.tools import filing_search
from src.rag import index
from tests import fixture_universe as fu


@pytest.fixture
def db(chunks_db):
    return chunks_db


def _search(universe, db, query, **kw):
    return filing_search(query, ticker=fu.TICKER, downloader=universe.downloader, db_path=db, **kw)


def test_10k_not_yet_public_is_never_returned(universe, db):
    before = _search(universe, db, "export restrictions", as_of="2024-02-19")
    assert before and fu.ACC_10K_2023 not in {h["accession_no"] for h in before}

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


def test_paraphrase_without_shared_keywords_finds_the_chunk(universe, db):
    query = "governmental bans hindering overseas trade"
    [hit, *_] = _search(universe, db, query, form="10-K", as_of=None)
    assert (hit["accession_no"], hit["section"]) == (fu.ACC_10K_2023, "Item 1A")
    assert not set(query.split()) & set(hit["text"].lower().split())


def test_as_of_holds_with_both_retrievers(universe, db):
    hits = _search(universe, db, "governmental bans hindering overseas trade", form="10-K",
                   as_of="2024-02-19")
    assert hits and {h["accession_no"] for h in hits} == {fu.ACC_10K_2022}


def test_table_of_contents_is_skipped(universe, db):
    hits = _search(universe, db, "table of contents", as_of=None)
    assert not any("| 22 |" in h["text"] for h in hits)
    with sqlite3.connect(db) as conn:
        texts = [t for (t,) in conn.execute("SELECT text FROM chunks")]
    assert not any("| 22 |" in t for t in texts)  # TOC page numbers


def test_section_filter_limits_results(universe, db):
    hits = _search(universe, db, "foreign currency exchange", section="Item 7A", as_of=None)
    assert hits and {h["section"] for h in hits} == {"Item 7A"}


def test_sections_indexed_per_form(universe, db):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT DISTINCT form, section FROM chunks").fetchall()
    by_form: dict[str, set[str]] = {}
    for form, section in rows:
        by_form.setdefault(form, set()).add(section)
    assert by_form == {
        "10-K": {"Item 1", "Item 1A", "Item 7", "Item 7A", "Item 8", "Item 9A"},
        "10-K/A": {"Item 10", "Item 11"},  # an Amendment keeps every Item it contains
        "10-Q": {"Part I Item 1", "Part I Item 2", "Part II Item 1A", "Part II Item 2"},
        "8-K": {"Ex-99.1"},
    }


def test_10q_sections_carry_their_part(universe, db):
    risk = _search(universe, db, "tariff on imported chips", section="Part II Item 1A", as_of=None)
    assert "tariff" in risk[0]["text"]
    assert (risk[0]["form"], risk[0]["fiscal_year"], risk[0]["fiscal_period"]) == ("10-Q", 2024, "Q1")

    mdna = _search(universe, db, "tariff on imported chips", section="Part I Item 2", as_of=None)
    assert mdna and not any("tariff" in h["text"] for h in mdna)


def test_after_hours_exhibit_is_searchable_from_its_acceptance_time(universe, db):
    query = "fourth quarter full year results"
    assert _search(universe, db, query, form="8-K", as_of="2024-02-15T17:44") == []

    [hit] = _search(universe, db, query, form="8-K", as_of="2024-02-15T17:45")
    assert (hit["accession_no"], hit["section"]) == (fu.ACC_8K_LATE, "Ex-99.1")
    assert hit["url"].endswith(fu.EX_99_1)
    assert hit["fiscal_period"] is None


def test_amendment_is_its_own_filing_and_never_the_latest_original(universe, db):
    query = "Chief Executive Officer compensation"
    [hit, *_] = _search(universe, db, query, as_of=None)
    assert (hit["accession_no"], hit["form"], hit["is_amendment"]) == (fu.ACC_10KA_2023, "10-K/A", True)

    latest = _search(universe, db, query, form="10-K", latest=True, as_of=None)
    assert latest and {h["accession_no"] for h in latest} == {fu.ACC_10K_2023}

    amended = _search(universe, db, query, form="10-K/A", latest=True, as_of=None)
    assert {h["accession_no"] for h in amended} == {fu.ACC_10KA_2023}
    by_accession = _search(universe, db, query, accession_no=fu.ACC_10K_2022, as_of=None)
    assert by_accession and {h["accession_no"] for h in by_accession} == {fu.ACC_10K_2022}


def test_latest_respects_as_of(universe, db):
    hits = _search(universe, db, "revenue", form="10-K", latest=True, as_of="2024-02-19")
    assert hits and {h["accession_no"] for h in hits} == {fu.ACC_10K_2022}


def test_reindexing_replaces_chunks(universe, db):
    first = index.index_company(universe.downloader, fu.TICKER, db)
    second = index.index_company(universe.downloader, fu.TICKER, db)
    with sqlite3.connect(db) as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    assert first == second
    assert total == sum(second.values()) == index.collection(db).count()


def test_filing_without_sections_is_skipped_with_warning(universe, tmp_path, capsys):
    folder = universe.downloader.filings_dir / str(fu.CIK) / fu.ACC_10K_2022
    (folder / fu.DOCS[fu.ACC_10K_2022]).write_bytes(b"<html><body><p>No items here.</p></body></html>")

    counts = index.index_company(universe.downloader, fu.TICKER, tmp_path / "chunks.db")
    assert counts[fu.ACC_10K_2022] == 0
    assert f"{fu.ACC_10K_2022}: no Sections found" in capsys.readouterr().out
