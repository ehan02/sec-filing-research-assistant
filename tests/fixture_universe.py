"""A small, fictional fixture Universe served through the fake EDGAR.

One Company, Fixture Corp (Ticker ``FIXT``, CIK 1234567, fiscal year ending
31 December), with Filings chosen to hit the point-in-time and parsing edge
cases later tickets test against:

========================  ======  ====================  ===========================
Accession                 Form    Availability (ET)     Why it's here
========================  ======  ====================  ===========================
ACC_10K_2022              10-K    2023-02-21 08:00:00   prior year for Section Diffs
ACC_8K_LATE               8-K     2024-02-15 17:45:00   after 17:30, so its filing
                                                        date rolls to 2024-02-16;
                                                        carries Ex-99.1
ACC_10K_2023              10-K    2024-02-20 08:00:00   TOC, all Items, a table;
                                                        restates FY2022 net income
ACC_10KA_2023             10-K/A  2024-04-29 16:05:00   Part III only
ACC_10Q_2024Q1            10-Q    2024-05-01 16:10:00   Part I Item 2 and
                                                        Part II Item 1A
========================  ======  ====================  ===========================

Facts (companyfacts) cover the Fiscal Year cases:

- ``Revenues`` FY2022 = 1000 in the FY2022 10-K, repeated identically in the
  FY2023 10-K: a comparative, not a Restatement. The repeat is tagged
  ``fy=2023`` the way XBRL does it (ADR-0002).
- ``NetIncomeLoss`` FY2022 = 100 in the FY2022 10-K, restated to 90 in the
  FY2023 10-K: a Restatement.
- ``Revenues`` FY2023 = 1200, and Q1 2024 = 330 from the 10-Q.
- One Fact cites ``ACC_UNKNOWN``, an accession number not in the submissions
  list, so it has no Availability Time and must be skipped.
"""

from __future__ import annotations

from datetime import datetime

from src.filings.availability import EASTERN

CIK = 1234567
TICKER = "FIXT"
COMPANY = "Fixture Corp"

ACC_10K_2022 = "0001234567-23-000010"
ACC_8K_LATE = "0001234567-24-000005"
ACC_10K_2023 = "0001234567-24-000010"
ACC_10KA_2023 = "0001234567-24-000020"
ACC_10Q_2024Q1 = "0001234567-24-000030"
ACC_UNKNOWN = "0009999999-24-000001"

# Expected Availability Times, US Eastern.
AVAILABILITY = {
    ACC_10K_2022: datetime(2023, 2, 21, 8, 0, 0, tzinfo=EASTERN),
    ACC_8K_LATE: datetime(2024, 2, 15, 17, 45, 0, tzinfo=EASTERN),
    ACC_10K_2023: datetime(2024, 2, 20, 8, 0, 0, tzinfo=EASTERN),
    ACC_10KA_2023: datetime(2024, 4, 29, 16, 5, 0, tzinfo=EASTERN),
    ACC_10Q_2024Q1: datetime(2024, 5, 1, 16, 10, 0, tzinfo=EASTERN),
}

DOCS = {
    ACC_10K_2022: "fixt-20221231.htm",
    ACC_8K_LATE: "fixt-20240215.htm",
    ACC_10K_2023: "fixt-20231231.htm",
    ACC_10KA_2023: "fixt-20231231a.htm",
    ACC_10Q_2024Q1: "fixt-20240331.htm",
}
EX_99_1 = "fixt-ex991_20240215.htm"

# Submissions rows, oldest first. acceptanceDateTime is UTC, as EDGAR sends it.
_ROWS = [
    # accession,      form,    filingDate,   reportDate,   acceptanceDateTime (UTC)
    (ACC_10K_2022, "10-K", "2023-02-21", "2022-12-31", "2023-02-21T13:00:00.000Z"),
    (ACC_8K_LATE, "8-K", "2024-02-16", "2024-02-15", "2024-02-15T22:45:00.000Z"),
    (ACC_10K_2023, "10-K", "2024-02-20", "2023-12-31", "2024-02-20T13:00:00.000Z"),
    (ACC_10KA_2023, "10-K/A", "2024-04-29", "2023-12-31", "2024-04-29T20:05:00.000Z"),
    (ACC_10Q_2024Q1, "10-Q", "2024-05-01", "2024-03-31", "2024-05-01T20:10:00.000Z"),
]


def _submissions() -> dict:
    rows = list(reversed(_ROWS))  # EDGAR lists newest first
    return {
        "cik": str(CIK),
        "name": COMPANY,
        "fiscalYearEnd": "1231",
        "filings": {
            "recent": {
                "accessionNumber": [r[0] for r in rows],
                "form": [r[1] for r in rows],
                "filingDate": [r[2] for r in rows],
                "reportDate": [r[3] for r in rows],
                "acceptanceDateTime": [r[4] for r in rows],
                "primaryDocument": [DOCS[r[0]] for r in rows],
                "primaryDocDescription": [r[1] for r in rows],
                "isXBRL": [0 if r[1] == "8-K" else 1 for r in rows],
            },
            "files": [],
        },
    }


# -- documents ------------------------------------------------------------------

_TOC = """
<table>
<tr><td>Item 1.</td><td>Business</td><td>3</td></tr>
<tr><td>Item 1A.</td><td>Risk Factors</td><td>5</td></tr>
<tr><td>Item 7.</td><td>Management's Discussion and Analysis</td><td>12</td></tr>
<tr><td>Item 7A.</td><td>Quantitative and Qualitative Disclosures About Market Risk</td><td>20</td></tr>
<tr><td>Item 8.</td><td>Financial Statements and Supplementary Data</td><td>22</td></tr>
<tr><td>Item 9A.</td><td>Controls and Procedures</td><td>40</td></tr>
</table>
"""


def _ten_k(year: int, risks: list[str], revenue: int, prior_revenue: int) -> bytes:
    risk_html = "\n".join(f"<p>{r}</p>" for r in risks)
    return f"""<html><body>
<p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>
<p>FORM 10-K</p>
<p>For the fiscal year ended December 31, {year}</p>
<p>Fixture Corp</p>
<p>TABLE OF CONTENTS</p>
{_TOC}
<p>PART I</p>
<p><b>Item 1. Business</b></p>
<p>Fixture Corp designs industrial sensors and sells them to manufacturers worldwide.</p>
<p><b>Item 1A. Risk Factors</b></p>
{risk_html}
<p><b>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</b></p>
<p>Revenue for fiscal {year} was ${revenue} million compared with ${prior_revenue} million in fiscal {year - 1}.</p>
<p>Table 1: Revenue by segment (in millions)</p>
<table>
<tr><th>Segment</th><th>{year}</th><th>{year - 1}</th></tr>
<tr><td>Sensors</td><td>{revenue - 200}</td><td>{prior_revenue - 200}</td></tr>
<tr><td>Services</td><td>200</td><td>200</td></tr>
<tr><td>Total</td><td>{revenue}</td><td>{prior_revenue}</td></tr>
</table>
<p><b>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</b></p>
<p>We are exposed to foreign currency risk on sales denominated in euros.</p>
<p><b>Item 8. Financial Statements and Supplementary Data</b></p>
<p>The consolidated financial statements appear on the following pages.</p>
<p><b>Item 9A. Controls and Procedures</b></p>
<p>Management concluded that internal control over financial reporting was effective.</p>
<p>PART III</p>
<p><b>Item 10. Directors, Executive Officers and Corporate Governance</b></p>
<p>Incorporated by reference to the proxy statement.</p>
</body></html>""".encode()


_RISKS_2022 = [
    "We depend on a single supplier for our sensor chips.",
    "Our sales are concentrated among a small number of customers.",
    "Changes in foreign exchange rates could reduce our reported revenue.",
]
_RISKS_2023 = [
    "We depend on a single supplier for our sensor chips.",
    "Our sales are concentrated among a small number of customers.",
    "New export restrictions could prevent us from selling sensors in certain markets.",
    # Reworded from FY2022: a Section Diff reports it as changed, not added.
    "Changes in foreign exchange rates could reduce our reported revenue and margins.",
]

TEN_K_2022 = _ten_k(2022, _RISKS_2022, revenue=1000, prior_revenue=900)
TEN_K_2023 = _ten_k(2023, _RISKS_2023, revenue=1200, prior_revenue=1000)

TEN_K_A_2023 = b"""<html><body>
<p>FORM 10-K/A</p>
<p>Amendment No. 1</p>
<p>Fixture Corp is filing this Amendment solely to include the Part III information.</p>
<p>PART III</p>
<p><b>Item 10. Directors, Executive Officers and Corporate Governance</b></p>
<p>Jane Example has served as Chief Executive Officer since 2019.</p>
<p><b>Item 11. Executive Compensation</b></p>
<p>Total compensation for the Chief Executive Officer was $2.1 million.</p>
</body></html>"""

TEN_Q_2024Q1 = b"""<html><body>
<p>FORM 10-Q</p>
<p>For the quarterly period ended March 31, 2024</p>
<p>PART I. FINANCIAL INFORMATION</p>
<p><b>Item 1. Financial Statements</b></p>
<p>Condensed consolidated financial statements (unaudited).</p>
<p><b>Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations</b></p>
<p>Revenue for the first quarter was $330 million, up 10% year over year.</p>
<p>PART II. OTHER INFORMATION</p>
<p><b>Item 1A. Risk Factors</b></p>
<p>There have been no material changes to the risk factors in our 2023 Form 10-K, except that a new tariff on imported chips could raise our costs.</p>
<p><b>Item 2. Unregistered Sales of Equity Securities and Use of Proceeds</b></p>
<p>We repurchased 1.5 million shares during the quarter.</p>
</body></html>"""

EIGHT_K_LATE = b"""<html><body>
<p>FORM 8-K</p>
<p><b>Item 2.02 Results of Operations and Financial Condition</b></p>
<p>On February 15, 2024, Fixture Corp issued a press release announcing its fourth quarter results, attached as Exhibit 99.1.</p>
<p><b>Item 9.01 Financial Statements and Exhibits</b></p>
<p>Exhibit 99.1 Press release dated February 15, 2024.</p>
</body></html>"""

EX_99_1_LATE = b"""<html><body>
<p>Exhibit 99.1</p>
<p>Fixture Corp Reports Fourth Quarter and Full Year 2023 Results</p>
<p>Full-year revenue was $1,200 million. The company expects fiscal 2024 revenue growth in the high single digits.</p>
</body></html>"""

INDEX_8K_LATE = {"directory": {"item": [
    {"name": DOCS[ACC_8K_LATE]},
    {"name": EX_99_1},
    {"name": "R1.htm"},
]}}


# -- XBRL companyfacts ------------------------------------------------------------

def _fact(start: str | None, end: str, val: int, accn: str, fy: int, fp: str,
          form: str, filed: str) -> dict:
    row = {"end": end, "val": val, "accn": accn, "fy": fy, "fp": fp,
           "form": form, "filed": filed}
    if start is not None:
        row["start"] = start
    return row


COMPANYFACTS = {
    "cik": CIK,
    "entityName": COMPANY,
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {"USD": [
                    _fact("2022-01-01", "2022-12-31", 1_000_000_000, ACC_10K_2022, 2022, "FY", "10-K", "2023-02-21"),
                    # Identical comparative, tagged with the reporting Filing's fy.
                    _fact("2022-01-01", "2022-12-31", 1_000_000_000, ACC_10K_2023, 2023, "FY", "10-K", "2024-02-20"),
                    _fact("2023-01-01", "2023-12-31", 1_200_000_000, ACC_10K_2023, 2023, "FY", "10-K", "2024-02-20"),
                    _fact("2024-01-01", "2024-03-31", 330_000_000, ACC_10Q_2024Q1, 2024, "Q1", "10-Q", "2024-05-01"),
                    # Reported by a Filing missing from the submissions list.
                    _fact("2023-01-01", "2023-12-31", 1_250_000_000, ACC_UNKNOWN, 2023, "FY", "10-K", "2024-03-01"),
                ]},
            },
            "NetIncomeLoss": {
                "label": "Net Income (Loss)",
                "units": {"USD": [
                    _fact("2022-01-01", "2022-12-31", 100_000_000, ACC_10K_2022, 2022, "FY", "10-K", "2023-02-21"),
                    # Restatement: same period, different value.
                    _fact("2022-01-01", "2022-12-31", 90_000_000, ACC_10K_2023, 2023, "FY", "10-K", "2024-02-20"),
                    _fact("2023-01-01", "2023-12-31", 150_000_000, ACC_10K_2023, 2023, "FY", "10-K", "2024-02-20"),
                ]},
            },
        },
    },
}


def routes() -> dict[str, object]:
    """URL-suffix routes for the fake EDGAR that serve the fixture Universe."""
    acc = lambda a: a.replace("-", "")  # noqa: E731
    return {
        "company_tickers.json": {"0": {"cik_str": CIK, "ticker": TICKER, "title": COMPANY}},
        f"submissions/CIK{CIK:010d}.json": _submissions(),
        f"companyfacts/CIK{CIK:010d}.json": COMPANYFACTS,
        f"{acc(ACC_10K_2022)}/{DOCS[ACC_10K_2022]}": TEN_K_2022,
        f"{acc(ACC_10K_2023)}/{DOCS[ACC_10K_2023]}": TEN_K_2023,
        f"{acc(ACC_10KA_2023)}/{DOCS[ACC_10KA_2023]}": TEN_K_A_2023,
        f"{acc(ACC_10Q_2024Q1)}/{DOCS[ACC_10Q_2024Q1]}": TEN_Q_2024Q1,
        f"{acc(ACC_8K_LATE)}/{DOCS[ACC_8K_LATE]}": EIGHT_K_LATE,
        f"{acc(ACC_8K_LATE)}/{EX_99_1}": EX_99_1_LATE,
        f"{acc(ACC_8K_LATE)}/index.json": INDEX_8K_LATE,
    }
