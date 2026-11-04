"""Point-in-time financial Facts, tested through get_financials on the fixture Universe."""

from __future__ import annotations

from datetime import date

import pytest

from src.agents.tools import get_financials
from src.filings.xbrl import fact_history, fiscal_year, load_facts
from tests import fixture_universe as fu

REVENUE = "us-gaap:Revenues"
NET_INCOME = "us-gaap:NetIncomeLoss"


@pytest.fixture
def db(universe, tmp_path):
    path = tmp_path / "facts.db"
    report = load_facts(universe.downloader, fu.TICKER, path)
    universe.report = report
    return path


def _ask(universe, db, concept, period, as_of):
    [row] = get_financials(fu.TICKER, [concept], [period], as_of,
                           downloader=universe.downloader, db_path=db)
    return row


def test_restatement_is_invisible_until_its_filing_is_public(universe, db):
    before = _ask(universe, db, NET_INCOME, "FY2022", "2024-02-19")
    after = _ask(universe, db, NET_INCOME, "FY2022", "2024-02-20")

    assert (before["value"], before["accession_no"]) == (100_000_000, fu.ACC_10K_2022)
    assert (after["value"], after["accession_no"]) == (90_000_000, fu.ACC_10K_2023)
    assert after["availability_time"] == fu.AVAILABILITY[fu.ACC_10K_2023]


def test_comparative_in_later_10k_is_returned_under_its_own_fiscal_year(universe, db):
    # The FY2023 10-K repeats FY2022 revenue tagged fy=2023; it must stay FY2022.
    fy2022 = _ask(universe, db, REVENUE, "FY2022", "2024-06-01")
    fy2023 = _ask(universe, db, REVENUE, "FY2023", "2024-06-01")

    assert (fy2022["value"], fy2022["accession_no"]) == (1_000_000_000, fu.ACC_10K_2023)
    assert (fy2023["value"], fy2023["unit"]) == (1_200_000_000, "USD")


def test_quarter_is_available_only_after_its_10q(universe, db):
    assert _ask(universe, db, REVENUE, "FY2024 Q1", "2024-05-01T16:09")["value"] is None
    assert _ask(universe, db, REVENUE, "FY2024 Q1", "2024-05-01T16:10")["value"] == 330_000_000


def test_identical_comparative_is_not_a_restatement(universe, db):
    assert len(fact_history(db, fu.CIK, REVENUE, 2022, "FY")) == 1
    restated = fact_history(db, fu.CIK, NET_INCOME, 2022, "FY")
    assert [f["value"] for f in restated] == [100_000_000, 90_000_000]


def test_fact_with_unknown_accession_is_skipped_and_reported(universe, db):
    assert universe.report["unknown_accession"] == 1
    # The skipped 1.25bn value never appears.
    assert _ask(universe, db, REVENUE, "FY2023", None)["value"] == 1_200_000_000


def test_ticker_input_resolves_to_cik(universe, db):
    rows = get_financials("fixt", [REVENUE, NET_INCOME], ["FY2022", "FY2023"], "2024-06-01",
                          downloader=universe.downloader, db_path=db)
    assert [(r["concept"], r["period"], r["value"]) for r in rows] == [
        (REVENUE, "FY2022", 1_000_000_000), (NET_INCOME, "FY2022", 90_000_000),
        (REVENUE, "FY2023", 1_200_000_000), (NET_INCOME, "FY2023", 150_000_000),
    ]


@pytest.mark.parametrize("end, fye, expected", [
    (date(2023, 9, 30), "0928", 2023),   # AAPL FY2023 ends two days after nominal
    (date(2022, 9, 24), "0928", 2022),   # AAPL FY2022 ends four days before
    (date(2023, 12, 30), "0928", 2024),  # AAPL Q1 FY2024
    (date(2023, 1, 1), "1231", 2022),    # 52/53-week year ending just after New Year
    (date(2023, 4, 30), "0131", 2024),   # retailer: year ending Jan 2024 is FY2024
])
def test_fiscal_year_handles_52_53_week_years(end, fye, expected):
    assert fiscal_year(end, fye) == expected
