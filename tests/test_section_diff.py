"""section_diff on the fixture Universe."""

from __future__ import annotations

import pytest

from src.agents.tools import section_diff
from tests import fixture_universe as fu

NEW_RISK = "New export restrictions could prevent us from selling sensors in certain markets."
FX_2022 = "Changes in foreign exchange rates could reduce our reported revenue."
FX_2023 = "Changes in foreign exchange rates could reduce our reported revenue and margins."


def _diff(universe, *args, **kw):
    return section_diff(fu.TICKER, *args, downloader=universe.downloader, **kw)


def test_reports_added_and_removed_paragraphs_with_citations(universe):
    diff = _diff(universe, "Item 1A", "10-K", 2022, 2023, as_of="2024-06-01")

    assert diff["added"] == [NEW_RISK]
    assert diff["removed"] == []
    assert diff["changed"] == [(FX_2022, FX_2023)]  # a rewording, not added + removed
    assert 0 < diff["similarity"] < 1
    assert (diff["citation_a"]["accession_no"], diff["citation_a"]["fiscal_year"]) == (fu.ACC_10K_2022, 2022)
    assert (diff["citation_b"]["accession_no"], diff["citation_b"]["section"]) == (fu.ACC_10K_2023, "Item 1A")
    assert diff["citation_b"]["availability_time"] == fu.AVAILABILITY[fu.ACC_10K_2023]


def test_reversed_years_report_the_paragraph_as_removed(universe):
    diff = _diff(universe, "Item 1A", "10-K", 2023, 2022, as_of=None)
    assert (diff["added"], diff["removed"]) == ([], [NEW_RISK])
    assert diff["changed"] == [(FX_2023, FX_2022)]


def test_identical_sections_score_one(universe):
    diff = _diff(universe, "Item 1A", "10-K", 2023, 2023, as_of=None)
    assert diff["similarity"] == pytest.approx(1.0)
    assert (diff["added"], diff["removed"], diff["changed"]) == ([], [], [])


def test_filing_not_yet_public_is_refused(universe):
    with pytest.raises(ValueError, match="not public"):
        _diff(universe, "Item 1A", "10-K", 2022, 2023, as_of="2024-02-19")


def test_missing_section_is_refused(universe):
    with pytest.raises(ValueError, match="has no Item 10"):
        _diff(universe, "Item 10", "10-K", 2022, 2023, as_of=None)


def test_fiscal_year_resolves_to_the_original_not_the_amendment(universe):
    # FY2023 has both a 10-K and a Part III-only 10-K/A; "10-K" means the Original.
    diff = _diff(universe, "Item 1A", "10-K", 2023, 2023, as_of=None)
    assert diff["citation_a"]["accession_no"] == fu.ACC_10K_2023

    with pytest.raises(ValueError, match="Expected one 10-K/A for FIXT FY2022"):
        _diff(universe, "Item 10", "10-K/A", 2022, 2023, as_of=None)
