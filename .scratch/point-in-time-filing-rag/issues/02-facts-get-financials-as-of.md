# 02: Facts tracer: `get_financials` as-of

**What to build:** A researcher asks `get_financials` for a Company's concepts over Fiscal Years at an As-of and gets back only values that were public then. Each value comes with the accession number and Availability Time of the Filing that reported it. Fiscal Year and Fiscal Period describe the period each value covers (ADR-0002), and later Restatements never leak backwards.

**Blocked by:** 01 (Downloader: amendments, Availability Time, fixture Universe)

**Status:** ready-for-agent

- [ ] companyfacts load into the facts table with: CIK, concept, unit, value, period dates, Fiscal Year, Fiscal Period, form, accession number, and Availability Time. The table has no Ticker column.
- [ ] Fiscal Year and Fiscal Period are derived from the period dates and the Company's fiscal year end, with a few days' tolerance for 52/53-week years. The raw `fy`/`fp` fields are never exposed under those names.
- [ ] A Fact whose accession number has no known Availability Time is skipped and counted in a load report.
- [ ] `get_fact` returns the value with the latest Availability Time at or before As-of, plus its accession number.
- [ ] A companion query lists every distinct value reported for a (CIK, concept, unit, period) over time, so Restatements can be told apart from repeated comparatives.
- [ ] The `get_financials` tool takes a Ticker, concepts, periods and As-of, resolves the Ticker to a CIK, and returns a table of values with their accession numbers and Availability Times.
- [ ] Tests through the tool, on the fixture Universe:
  - a restated value is invisible before its Filing's Availability Time and visible after it;
  - FY2022 revenue repeated in a FY2024 10-K is returned as FY2022;
  - an identical comparative is not reported as a Restatement;
  - Ticker input resolves to CIK.
