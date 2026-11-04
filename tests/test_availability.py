"""Availability Time and As-of: amendments, acceptance times and the As-of rule.

Run against the fixture Universe through the fake EDGAR.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from src.filings.availability import (EASTERN, is_available, normalize_as_of,
                                      parse_acceptance)
from tests import fixture_universe as fu


def _metadata(universe, accession: str) -> dict:
    path = universe.data_dir / "filings" / str(fu.CIK) / accession / "metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))


# -- amendments ---------------------------------------------------------------------

def test_asking_for_a_form_also_selects_its_amendments(universe):
    records = universe.downloader.list_filings(fu.TICKER, forms=["10-K"],
                                               since=date(2023, 1, 1))
    assert [(r.form, r.is_amendment) for r in records] == [
        ("10-K", False), ("10-K", False), ("10-K/A", True)]


def test_amendment_is_saved_as_its_own_filing(universe):
    original = _metadata(universe, fu.ACC_10K_2023)
    amendment = _metadata(universe, fu.ACC_10KA_2023)

    assert original["is_amendment"] is False
    assert amendment["is_amendment"] is True
    assert amendment["form"] == "10-K/A"
    assert amendment["files"] == [fu.DOCS[fu.ACC_10KA_2023]]


def test_8k_keeps_its_exhibit_99(universe):
    assert _metadata(universe, fu.ACC_8K_LATE)["files"] == [
        fu.DOCS[fu.ACC_8K_LATE], fu.EX_99_1]


# -- Availability Time --------------------------------------------------------------

@pytest.mark.parametrize("accession", list(fu.AVAILABILITY))
def test_metadata_records_availability_time_in_eastern(universe, accession):
    saved = datetime.fromisoformat(_metadata(universe, accession)["availability_time"])
    assert saved == fu.AVAILABILITY[accession]
    assert saved.utcoffset() == fu.AVAILABILITY[accession].astimezone(EASTERN).utcoffset()


def test_after_hours_8k_is_available_on_acceptance_day_not_filing_date(universe):
    meta = _metadata(universe, fu.ACC_8K_LATE)
    available = datetime.fromisoformat(meta["availability_time"])

    assert meta["filing_date"] == "2024-02-16"  # EDGAR rolled it to the next day
    assert available.date() == date(2024, 2, 15)
    assert (available.hour, available.minute) == (17, 45)


def test_acceptance_z_suffix_is_utc():
    # AAPL 8-K 0000320193-26-000024: API 21:30:23Z, EDGAR index "Accepted 16:30:23" (EST).
    assert parse_acceptance("2026-11-02T21:30:23.000Z") == datetime(2026, 11, 2, 16, 30, 23,
                                                                    tzinfo=EASTERN)
    # 0000320193-26-000018: API 20:30:28Z, index 16:30:28 (EDT).
    assert parse_acceptance("2026-07-30T20:30:28.000Z") == datetime(2026, 7, 30, 16, 30, 28,
                                                                    tzinfo=EASTERN)
    assert parse_acceptance("") is None
    assert parse_acceptance(None) is None


def test_accession_lookup_covers_every_filing(universe):
    times = universe.downloader.availability_times(fu.TICKER)
    assert times == fu.AVAILABILITY
    assert fu.ACC_UNKNOWN not in times


def test_accession_lookup_reads_older_submissions_files(tmp_path, monkeypatch):
    from tests.fakes import FakeEdgar, make_downloader

    routes = fu.routes()
    name = f"CIK{fu.CIK:010d}"
    sub = routes[f"submissions/{name}.json"]
    sub["filings"]["files"] = [{"name": f"{name}-submissions-001.json",
                                "filingFrom": "2001-01-01", "filingTo": "2010-12-31"}]
    routes[f"submissions/{name}-submissions-001.json"] = {
        "accessionNumber": ["0001234567-05-000001"], "form": ["S-1"],
        "filingDate": ["2005-03-01"], "reportDate": [""],
        "acceptanceDateTime": ["2005-03-01T15:00:00.000Z"],
        "primaryDocument": ["s1.htm"], "primaryDocDescription": ["S-1"], "isXBRL": [0],
    }
    downloader = make_downloader(tmp_path, FakeEdgar(routes), monkeypatch)

    times = downloader.availability_times(fu.TICKER)
    assert times["0001234567-05-000001"] == datetime(2005, 3, 1, 10, 0, tzinfo=EASTERN)


# -- As-of ----------------------------------------------------------------------------

def test_date_only_as_of_is_end_of_day_eastern():
    as_of = normalize_as_of(date(2024, 2, 15))
    assert as_of == datetime(2024, 2, 15, 23, 59, 59, 999999, tzinfo=EASTERN)
    assert normalize_as_of("2024-02-15") == as_of


def test_naive_datetime_as_of_is_eastern_and_aware_one_is_converted():
    assert normalize_as_of(datetime(2024, 2, 15, 17, 45)) == datetime(2024, 2, 15, 17, 45,
                                                                      tzinfo=EASTERN)
    utc = datetime(2024, 2, 15, 22, 45, tzinfo=timezone.utc)
    assert normalize_as_of(utc) == datetime(2024, 2, 15, 17, 45, tzinfo=EASTERN)
    assert normalize_as_of("2024-02-15T22:45:00Z") == normalize_as_of(utc)


def test_missing_as_of_means_now():
    before = datetime.now(EASTERN)
    as_of = normalize_as_of(None)
    assert before <= as_of <= datetime.now(EASTERN)
    assert as_of.tzinfo is not None


def test_minute_before_and_after_acceptance(universe):
    accepted = universe.downloader.availability_times(fu.TICKER)[fu.ACC_8K_LATE]
    minute = timedelta(minutes=1)

    assert not is_available(accepted, normalize_as_of(accepted - minute))
    assert is_available(accepted, normalize_as_of(accepted))
    assert is_available(accepted, normalize_as_of(accepted + minute))


def test_date_only_as_of_on_acceptance_day_includes_after_hours_filing(universe):
    accepted = universe.downloader.availability_times(fu.TICKER)[fu.ACC_8K_LATE]

    assert is_available(accepted, normalize_as_of("2024-02-15"))
    assert not is_available(accepted, normalize_as_of("2024-02-14"))


def test_unknown_availability_is_never_available():
    assert not is_available(None, normalize_as_of(None))
