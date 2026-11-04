"""Offline tests for the EDGAR downloader. All HTTP calls are faked."""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.filings.edgar import EdgarClient, EdgarDownloader, main
from tests.fakes import FakeEdgar, make_downloader
from tests.fakes import response as _response

CIK = 320193
ACC_10K = "0000320193-24-000123"
ACC_8K = "0000320193-24-000081"
ACC_OLD = "0000320193-19-000119"

TICKERS = {"0": {"cik_str": CIK, "ticker": "AAPL", "title": "Apple Inc."}}

SUBMISSIONS = {
    "name": "Apple Inc.",
    "filings": {
        "recent": {
            "accessionNumber": [ACC_10K, ACC_8K, "0000320193-24-000050"],
            "filingDate": ["2024-11-01", "2024-08-01", "2024-05-03"],
            "reportDate": ["2024-09-28", "2024-08-01", ""],
            "acceptanceDateTime": ["2024-11-01T06:01:36.000Z", "2024-08-01T16:30:00.000Z", ""],
            "form": ["10-K", "8-K", "4"],
            "primaryDocument": ["aapl-20240928.htm", "aapl-20240801.htm", "form4.xml"],
            "primaryDocDescription": ["10-K", "8-K", "FORM 4"],
            "isXBRL": [1, 1, 0],
        },
        "files": [
            {"name": "CIK0000320193-submissions-001.json",
             "filingFrom": "2015-01-01", "filingTo": "2019-12-31"},
        ],
    },
}

OLD_SUBMISSIONS = {
    "accessionNumber": [ACC_OLD],
    "filingDate": ["2019-10-31"],
    "reportDate": ["2019-09-28"],
    "acceptanceDateTime": ["2019-10-30T18:12:36.000Z"],
    "form": ["10-K"],
    "primaryDocument": ["a10-k20199282019.htm"],
    "primaryDocDescription": ["10-K"],
    "isXBRL": [1],
}

INDEX_8K = {"directory": {"item": [
    {"name": "aapl-20240801.htm"},
    {"name": "a8-kex991q3202406292024.htm"},
    {"name": "a8-kex992q3202406292024.htm"},
    {"name": "R1.htm"},
    {"name": "Financial_Report.xlsx"},
]}}


DEFAULT_ROUTES: dict[str, object] = {
    "company_tickers.json": TICKERS,
    "submissions/CIK0000320193.json": SUBMISSIONS,
    "submissions/CIK0000320193-submissions-001.json": {**OLD_SUBMISSIONS},
    "/aapl-20240928.htm": b"<html>10-K body</html>",
    "/aapl-20240801.htm": b"<html>8-K body</html>",
    "/index.json": INDEX_8K,
    "/a8-kex991q3202406292024.htm": b"<html>Earnings release</html>",
    "/a8-kex992q3202406292024.htm": b"<html>CFO commentary</html>",
    "/a10-k20199282019.htm": b"<html>old 10-K</html>",
    "companyfacts/CIK0000320193.json": {"cik": CIK, "facts": {}},
}


@pytest.fixture
def fake() -> FakeEdgar:
    return FakeEdgar(dict(DEFAULT_ROUTES))


@pytest.fixture
def downloader(tmp_path, fake, monkeypatch) -> EdgarDownloader:
    return make_downloader(tmp_path, fake, monkeypatch)


# -- client ---------------------------------------------------------------

@pytest.mark.parametrize("agent", ["", "YourName your-contact@example.com", "no contact"])
def test_client_rejects_missing_or_placeholder_user_agent(agent, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", agent)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        EdgarClient()


def test_client_retries_on_429(monkeypatch):
    client = EdgarClient(user_agent="Test Runner test@example.com", min_interval=0)
    statuses = iter([429, 503, 200])
    monkeypatch.setattr(client.session, "get",
                        lambda url, timeout: _response(url, status=next(statuses), payload={}))
    monkeypatch.setattr("src.filings.edgar.time.sleep", lambda s: None)
    assert client.get("https://example.test/x").status_code == 200


# -- ticker map and filing list ---------------------------------------------

def test_lookup_normalizes_ticker(downloader):
    assert downloader.lookup("aapl") == (CIK, "Apple Inc.")
    with pytest.raises(KeyError):
        downloader.lookup("ZZZZ")


def test_list_filings_filters_forms_and_dates(downloader, fake):
    records = downloader.list_filings("AAPL", forms=["10-K", "8-K"], since=date(2024, 1, 1))

    assert [r.accession_no for r in records] == [ACC_8K, ACC_10K]  # sorted by filing date
    tenk = records[1]
    assert tenk.report_date == date(2024, 9, 28)
    assert tenk.acceptance_datetime == "2024-11-01T06:01:36.000Z"
    assert tenk.url == ("https://www.sec.gov/Archives/edgar/data/320193/"
                        "000032019324000123/aapl-20240928.htm")
    # The 2015-2019 file is outside the window, so it is never fetched.
    assert not any("submissions-001" in c for c in fake.calls)


def test_list_filings_pages_into_older_files(downloader, fake):
    records = downloader.list_filings("AAPL", forms=["10-K"], since=date(2019, 1, 1))
    assert [r.accession_no for r in records] == [ACC_OLD, ACC_10K]
    assert any("submissions-001" in c for c in fake.calls)


def test_submissions_are_cached(downloader, fake):
    downloader.list_filings("AAPL", forms=["10-K"], since=date(2024, 1, 1))
    downloader.list_filings("AAPL", forms=["10-K"], since=date(2024, 1, 1))
    assert sum("submissions/CIK0000320193.json" in c for c in fake.calls) == 1


# -- documents --------------------------------------------------------------

def test_download_10k_writes_document_and_metadata(downloader, tmp_path):
    rec = downloader.list_filings("AAPL", forms=["10-K"], since=date(2024, 1, 1))[0]
    folder, downloaded = downloader.download_filing(rec)

    assert downloaded
    assert folder == tmp_path / "filings" / str(CIK) / ACC_10K
    assert (folder / "aapl-20240928.htm").read_bytes() == b"<html>10-K body</html>"
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["accession_no"] == ACC_10K
    assert meta["filing_date"] == "2024-11-01"
    assert meta["files"] == ["aapl-20240928.htm"]


def test_download_8k_includes_exhibit_99_only(downloader):
    rec = downloader.list_filings("AAPL", forms=["8-K"], since=date(2024, 1, 1))[0]
    folder, _ = downloader.download_filing(rec)

    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["files"] == ["aapl-20240801.htm",
                             "a8-kex991q3202406292024.htm",
                             "a8-kex992q3202406292024.htm"]
    assert (folder / "a8-kex991q3202406292024.htm").exists()
    assert not (folder / "R1.htm").exists()


def test_download_is_idempotent(downloader, fake):
    rec = downloader.list_filings("AAPL", forms=["10-K"], since=date(2024, 1, 1))[0]
    downloader.download_filing(rec)
    n_calls = len(fake.calls)

    _, downloaded = downloader.download_filing(rec)
    assert not downloaded
    assert len(fake.calls) == n_calls


def test_partial_download_is_retried(downloader):
    rec = downloader.list_filings("AAPL", forms=["10-K"], since=date(2024, 1, 1))[0]
    folder = downloader.filing_dir(rec)
    folder.mkdir(parents=True)
    (folder / "aapl-20240928.htm").write_bytes(b"truncated")  # no metadata.json

    _, downloaded = downloader.download_filing(rec)
    assert downloaded
    assert (folder / "aapl-20240928.htm").read_bytes() == b"<html>10-K body</html>"


# -- XBRL and universe ------------------------------------------------------

def test_companyfacts_missing_returns_none(downloader, fake):
    fake.routes["companyfacts/CIK0000320193.json"] = 404
    assert downloader.download_companyfacts("AAPL") is None


def test_universe_continues_past_failures(downloader, fake):
    fake.routes["/aapl-20240801.htm"] = 500
    summary = downloader.download_universe(["AAPL", "ZZZZ"], forms=["10-K", "8-K"],
                                           since=date(2024, 1, 1))

    assert summary["AAPL"] == {"listed": 2, "downloaded": 1, "cached": 0, "failed": 1}
    assert summary["ZZZZ"]["failed"] == 1


def test_cli_exits_cleanly_without_user_agent(monkeypatch, capsys):
    monkeypatch.setenv("SEC_USER_AGENT", "")
    monkeypatch.setattr("src.filings.edgar.load_dotenv", lambda *a, **k: None)
    assert main(["AAPL"]) == 1
