"""EDGAR downloader.

Ticker->CIK map, filing list from the submissions API, and a rate-limited,
cached download of raw filings into data/filings/{cik}/{accession}/.

Asking for a form also selects its Amendments (10-K selects 10-K/A); each
Amendment is saved as its own Filing.

Each filing folder holds the primary document, any 8-K Exhibit 99 files, and
a metadata.json with the fields later stages need for point-in-time
filtering and citations (accession number, Availability Time, amendment flag).
metadata.json is written last, so a folder without it is re-downloaded.

Usage
-----
    python -m src.filings.edgar AAPL MSFT NVDA
    python -m src.filings.edgar AAPL --forms 10-K --since 2020-01-01
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, computed_field

from src.filings.availability import parse_acceptance

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{name}"

DEFAULT_FORMS = ("10-K", "10-Q", "8-K")
PLACEHOLDER_AGENT = "YourName your-contact@example.com"
SUBMISSIONS_MAX_AGE = timedelta(hours=24)

_EX99_RE = re.compile(r"ex-?99", re.IGNORECASE)
_DOC_EXT = (".htm", ".html", ".txt")


def _emit(msg: str) -> None:
    """UTF-8-safe print that survives Windows cp1252 consoles."""
    sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
    sys.stdout.flush()


# ============================================================================
# HTTP client
# ============================================================================

class EdgarClient:
    """Polite EDGAR HTTP client: required User-Agent, rate limit, retries.

    SEC asks for a descriptive User-Agent with contact details and at most
    10 requests per second. The User-Agent comes from SEC_USER_AGENT in .env
    unless passed explicitly.
    """

    def __init__(self, user_agent: str | None = None,
                 min_interval: float = 0.15, max_retries: int = 4) -> None:
        load_dotenv(ROOT / ".env")
        agent = (user_agent or os.getenv("SEC_USER_AGENT", "")).strip()
        if not agent or agent == PLACEHOLDER_AGENT or "@" not in agent:
            raise RuntimeError(
                "Set SEC_USER_AGENT in .env to your name and contact email, "
                "e.g. 'Jane Doe jane@example.com'. SEC rejects requests without it."
            )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": agent,
                                     "Accept-Encoding": "gzip, deflate"})
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request = 0.0

    def get(self, url: str) -> requests.Response:
        """GET with rate limiting and exponential backoff on 429/5xx."""
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            resp = self.session.get(url, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError(f"unreachable: retries exhausted for {url}")


# ============================================================================
# Models
# ============================================================================

class FilingRecord(BaseModel):
    """One filing from the submissions API. Identity is the accession number."""

    cik: int
    ticker: str
    company: str
    form: str
    accession_no: str
    filing_date: date
    report_date: date | None = None
    acceptance_datetime: str | None = None
    primary_document: str
    primary_doc_description: str | None = None
    is_xbrl: bool = False

    @computed_field
    @property
    def is_amendment(self) -> bool:
        return self.form.upper().endswith("/A")

    @computed_field
    @property
    def availability_time(self) -> datetime | None:
        """When the Filing became public: acceptance datetime in US Eastern (ADR-0001)."""
        return parse_acceptance(self.acceptance_datetime)

    @property
    def accession_nodash(self) -> str:
        return self.accession_no.replace("-", "")

    def archive_url(self, name: str) -> str:
        return ARCHIVES_URL.format(cik=self.cik, acc_nodash=self.accession_nodash, name=name)

    @property
    def url(self) -> str:
        """EDGAR URL of the primary document, used in citations."""
        return self.archive_url(self.primary_document)


# ============================================================================
# Downloader
# ============================================================================

class EdgarDownloader:
    """Download filings and XBRL company facts into a local cache.

    Layout under ``data_dir``::

        cache/company_tickers.json
        cache/submissions/<name>.json
        cache/companyfacts/CIK##########.json
        filings/<cik>/<accession>/<primary doc, exhibits, metadata.json>
    """

    def __init__(self, client: EdgarClient, data_dir: Path = DATA_DIR) -> None:
        self.client = client
        self.cache_dir = data_dir / "cache"
        self.filings_dir = data_dir / "filings"
        self._tickers: dict[str, tuple[int, str]] | None = None

    # -- cached JSON -------------------------------------------------------

    def _cached_json(self, url: str, path: Path,
                     max_age: timedelta | None = None, refresh: bool = False) -> Any:
        if path.exists() and not refresh:
            age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
            if max_age is None or age < max_age:
                return json.loads(path.read_text(encoding="utf-8"))
        data = self.client.get(url).json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    # -- ticker -> CIK -----------------------------------------------------

    def ticker_map(self, refresh: bool = False) -> dict[str, tuple[int, str]]:
        """Return {TICKER: (cik, company title)} from SEC's company_tickers.json."""
        if self._tickers is None or refresh:
            raw = self._cached_json(TICKERS_URL, self.cache_dir / "company_tickers.json",
                                    max_age=timedelta(days=7), refresh=refresh)
            self._tickers = {row["ticker"].upper(): (int(row["cik_str"]), row["title"])
                             for row in raw.values()}
        return self._tickers

    def lookup(self, ticker: str) -> tuple[int, str]:
        key = ticker.upper().replace(".", "-")
        tickers = self.ticker_map()
        if key not in tickers:
            raise KeyError(f"Ticker {ticker!r} not found in SEC company_tickers.json")
        return tickers[key]

    # -- filing list -------------------------------------------------------

    def list_filings(self, ticker: str, forms: Iterable[str] = DEFAULT_FORMS,
                     since: date | None = None, refresh: bool = False) -> list[FilingRecord]:
        """List a company's filings of the given forms filed on or after ``since``.

        Each form also selects its Amendments (``10-K`` selects ``10-K/A``).
        """
        cik, title = self.lookup(ticker)
        wanted = _with_amendments(forms)
        sub, rows = self._submission_rows(cik, since, refresh)

        company = sub.get("name") or title
        records: dict[str, FilingRecord] = {}
        for row in rows:
            if row["form"].upper() not in wanted or not row.get("primaryDocument"):
                continue
            filed = date.fromisoformat(row["filingDate"])
            if since is not None and filed < since:
                continue
            records[row["accessionNumber"]] = FilingRecord(
                cik=cik,
                ticker=ticker.upper(),
                company=company,
                form=row["form"],
                accession_no=row["accessionNumber"],
                filing_date=filed,
                report_date=_parse_date(row.get("reportDate")),
                acceptance_datetime=row.get("acceptanceDateTime") or None,
                primary_document=row["primaryDocument"],
                primary_doc_description=row.get("primaryDocDescription") or None,
                is_xbrl=bool(row.get("isXBRL")),
            )
        return sorted(records.values(), key=lambda r: r.filing_date)

    def availability_times(self, ticker: str, refresh: bool = False) -> dict[str, datetime]:
        """Map every accession number the Company ever filed to its Availability Time.

        Covers all forms and the full submissions history, because XBRL Facts
        can be reported by any Filing (ADR-0001). Filings with no acceptance
        time are left out.
        """
        cik, _ = self.lookup(ticker)
        _, rows = self._submission_rows(cik, since=None, refresh=refresh)
        times: dict[str, datetime] = {}
        for row in rows:
            when = parse_acceptance(row.get("acceptanceDateTime"))
            if when is not None:
                times[row["accessionNumber"]] = when
        return times

    def _submission_rows(self, cik: int, since: date | None,
                         refresh: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """The Company's submissions JSON plus its filing rows on or after ``since``.

        The submissions API returns the most recent ~1000 filings inline and
        older ones in extra files; those are fetched only when ``since``
        reaches back into their date range (always, when ``since`` is None).
        """
        sub_dir = self.cache_dir / "submissions"
        name = f"CIK{cik:010d}.json"
        sub = self._cached_json(SUBMISSIONS_URL.format(name=name), sub_dir / name,
                                max_age=SUBMISSIONS_MAX_AGE, refresh=refresh)
        blocks = [sub["filings"]["recent"]]
        for extra in sub["filings"].get("files", []):
            if since is None or date.fromisoformat(extra["filingTo"]) >= since:
                blocks.append(self._cached_json(SUBMISSIONS_URL.format(name=extra["name"]),
                                                sub_dir / extra["name"]))
        return sub, [row for block in blocks for row in _columns_to_rows(block)]

    # -- documents ---------------------------------------------------------

    def filing_dir(self, rec: FilingRecord) -> Path:
        return self.filings_dir / str(rec.cik) / rec.accession_no

    def download_filing(self, rec: FilingRecord, refresh: bool = False) -> tuple[Path, bool]:
        """Download one filing. Returns (folder, downloaded) - False if cached."""
        folder = self.filing_dir(rec)
        meta_path = folder / "metadata.json"
        if meta_path.exists() and not refresh:
            return folder, False

        folder.mkdir(parents=True, exist_ok=True)
        files = [rec.primary_document]
        if rec.form.upper().startswith("8-K"):
            files += self._exhibit_99_names(rec)

        for name in files:
            (folder / name).write_bytes(self.client.get(rec.archive_url(name)).content)

        meta = rec.model_dump(mode="json") | {
            "url": rec.url,
            "files": files,
            "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return folder, True

    def _exhibit_99_names(self, rec: FilingRecord) -> list[str]:
        """Exhibit 99.x documents (earnings releases) in an 8-K's folder."""
        index = self.client.get(rec.archive_url("index.json")).json()
        names = [item["name"] for item in index.get("directory", {}).get("item", [])]
        return sorted(n for n in names
                      if _EX99_RE.search(n) and n.lower().endswith(_DOC_EXT)
                      and n != rec.primary_document)

    # -- XBRL --------------------------------------------------------------

    def download_companyfacts(self, ticker: str, refresh: bool = False) -> Path | None:
        """Cache a company's XBRL companyfacts JSON. None if SEC has none."""
        cik, _ = self.lookup(ticker)
        path = self.cache_dir / "companyfacts" / f"CIK{cik:010d}.json"
        try:
            self._cached_json(COMPANYFACTS_URL.format(cik=cik), path,
                              max_age=SUBMISSIONS_MAX_AGE, refresh=refresh)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return path

    # -- universe ----------------------------------------------------------

    def download_universe(self, tickers: Iterable[str], forms: Iterable[str] = DEFAULT_FORMS,
                          since: date | None = None, include_facts: bool = True,
                          refresh: bool = False) -> dict[str, dict[str, int]]:
        """Download filings (and companyfacts) for every ticker.

        A failure on one ticker or filing is reported and skipped so a long
        run is not lost; rerunning resumes from the cache.
        """
        forms = tuple(forms)
        summary: dict[str, dict[str, int]] = {}
        for ticker in tickers:
            stats = {"listed": 0, "downloaded": 0, "cached": 0, "failed": 0}
            summary[ticker.upper()] = stats
            try:
                records = self.list_filings(ticker, forms, since, refresh=refresh)
            except (KeyError, requests.RequestException) as exc:
                _emit(f"[{ticker.upper()}] cannot list filings: {exc}")
                stats["failed"] += 1
                continue

            stats["listed"] = len(records)
            _emit(f"[{ticker.upper()}] {len(records)} filings ({', '.join(forms)})")
            for rec in records:
                try:
                    _, downloaded = self.download_filing(rec, refresh=refresh)
                except requests.RequestException as exc:
                    _emit(f"  ! {rec.form} {rec.accession_no}: {exc}")
                    stats["failed"] += 1
                    continue
                stats["downloaded" if downloaded else "cached"] += 1
                if downloaded:
                    _emit(f"  + {rec.form:<5} filed {rec.filing_date}  {rec.accession_no}")

            if include_facts:
                try:
                    path = self.download_companyfacts(ticker, refresh=refresh)
                    _emit(f"  companyfacts: {'saved' if path else 'none on EDGAR'}")
                except requests.RequestException as exc:
                    _emit(f"  ! companyfacts: {exc}")
                    stats["failed"] += 1
        return summary


# ============================================================================
# Helpers
# ============================================================================

def _columns_to_rows(block: dict[str, list]) -> list[dict[str, Any]]:
    """The submissions API stores filings column-wise; zip into row dicts."""
    keys = list(block)
    return [dict(zip(keys, values)) for values in zip(*(block[k] for k in keys))]


def _with_amendments(forms: Iterable[str]) -> set[str]:
    """Upper-cased forms plus each one's Amendment form (10-K -> 10-K/A)."""
    wanted = {f.upper() for f in forms}
    return wanted | {f"{f}/A" for f in wanted if not f.endswith("/A")}


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


# ============================================================================
# CLI
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download SEC filings from EDGAR.")
    parser.add_argument("tickers", nargs="+", help="Tickers, e.g. AAPL MSFT")
    parser.add_argument("--forms", nargs="+", default=list(DEFAULT_FORMS),
                        help="Form types; each includes its /A amendments "
                             "(default: 10-K 10-Q 8-K)")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--since", type=date.fromisoformat,
                        help="Earliest filing date, YYYY-MM-DD")
    window.add_argument("--years", type=int, default=5,
                        help="Look back this many years (default: 5)")
    parser.add_argument("--no-facts", action="store_true", help="Skip XBRL companyfacts")
    parser.add_argument("--refresh", action="store_true", help="Ignore the local cache")
    args = parser.parse_args(argv)

    since = args.since or date.today() - timedelta(days=365 * args.years)
    try:
        client = EdgarClient()
    except RuntimeError as exc:
        _emit(f"Error: {exc}")
        return 1

    summary = EdgarDownloader(client).download_universe(
        args.tickers, args.forms, since,
        include_facts=not args.no_facts, refresh=args.refresh,
    )
    _emit("\nSummary")
    for ticker, s in summary.items():
        _emit(f"  {ticker:<6} listed {s['listed']:>4}  new {s['downloaded']:>4}  "
              f"cached {s['cached']:>4}  failed {s['failed']:>3}")
    return 1 if any(s["failed"] for s in summary.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
