"""The numeric and point-in-time eval sets, generated from the fixture Universe's Facts."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.filings.xbrl import load_facts
from tests import fixture_universe as fu
from tests.eval_filings import (
    financials_lookup,
    matches,
    numeric_set,
    point_in_time_set,
    run_numeric,
    run_point_in_time,
)

REVENUE = "us-gaap:Revenues"
NET_INCOME = "us-gaap:NetIncomeLoss"
TAX_RATE = "us-gaap:EffectiveIncomeTaxRateReconciliationAtFederalStatutoryIncomeTaxRate"  # ambiguous, skipped


@pytest.fixture
def db(universe, tmp_path):
    path = tmp_path / "facts.db"
    load_facts(universe.downloader, fu.TICKER, path)
    return path


def test_numeric_set_asks_each_value_as_first_reported(universe, db):
    questions = numeric_set(db, universe.downloader, [REVENUE, NET_INCOME, TAX_RATE])
    got = {(q["concept"], q["period"]): (q["expected"], q["as_of"], q["accession_no"]) for q in questions}
    assert got == {
        (REVENUE, "FY2022"): (1_000_000_000, fu.AVAILABILITY[fu.ACC_10K_2022], fu.ACC_10K_2022),
        (REVENUE, "FY2023"): (1_200_000_000, fu.AVAILABILITY[fu.ACC_10K_2023], fu.ACC_10K_2023),
        (REVENUE, "FY2024 Q1"): (330_000_000, fu.AVAILABILITY[fu.ACC_10Q_2024Q1], fu.ACC_10Q_2024Q1),
        (NET_INCOME, "FY2022"): (100_000_000, fu.AVAILABILITY[fu.ACC_10K_2022], fu.ACC_10K_2022),
        (NET_INCOME, "FY2023"): (150_000_000, fu.AVAILABILITY[fu.ACC_10K_2023], fu.ACC_10K_2023),
    }
    assert all(q["ticker"] == fu.TICKER for q in questions)

    report = run_numeric(questions, financials_lookup(universe.downloader, db), tolerance=0)
    assert (report["accuracy"], report["failures"]) == (1.0, [])


def test_point_in_time_set_straddles_each_restating_filing(universe, db):
    questions = point_in_time_set(db, universe.downloader)
    restated_at = fu.AVAILABILITY[fu.ACC_10K_2023]
    # Only net income was restated; FY2022 revenue's identical repeat is a comparative.
    assert [(q["concept"], q["period"], q["as_of"], q["expected"], q["restated_value"]) for q in questions] == [
        (NET_INCOME, "FY2022", restated_at - timedelta(seconds=1), 100_000_000, 90_000_000),
        (NET_INCOME, "FY2022", restated_at, 90_000_000, 90_000_000),
    ]
    report = run_point_in_time(questions, financials_lookup(universe.downloader, db), tolerance=0)
    assert (report["accuracy"], report["leaks"]) == (1.0, [])


def test_a_lookup_that_ignores_as_of_is_reported_as_a_leak_by_name(universe, db):
    questions = point_in_time_set(db, universe.downloader)
    honest = financials_lookup(universe.downloader, db)
    report = run_point_in_time(questions, lambda q: honest(q | {"as_of": None}), tolerance=0)

    assert report["accuracy"] == 0.5
    [leak] = report["leaks"]
    assert leak["id"].startswith(f"{fu.TICKER} {NET_INCOME} FY2022 before ")
    assert (leak["expected"], leak["actual"]) == (100_000_000, 90_000_000)


@pytest.mark.parametrize("actual, tolerance, ok", [
    (1_000_000_000, 0, True),
    (1_000_500_000, 0, False),
    (1_000_500_000, 0.001, True),
    (1_002_000_000, 0.001, False),
    (None, 0.5, False),
])
def test_values_match_within_a_relative_tolerance(actual, tolerance, ok):
    assert matches(1_000_000_000, actual, tolerance) is ok
