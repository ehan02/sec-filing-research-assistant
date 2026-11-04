# 07: `section_diff` tool

**What to build:** An analyst asks what changed in a Company's Section between two Fiscal Years. They get a similarity score, the paragraphs added and removed, and a Citation for each Filing. Both Filings must be public at the As-of.

**Blocked by:** 03 (Text tracer: `filing_search` over 10-K Sections (BM25))

**Status:** ready-for-agent

- [ ] `section_diff(ticker, section, form, fiscal_year_a, fiscal_year_b, as_of)` resolves the Ticker to a CIK and each Fiscal Year to the Original Filing of that form. An Amendment is used only if named explicitly.
- [ ] It returns a similarity score, the added and removed paragraphs, and both Filings' Citations.
- [ ] It fails with a clear error if either Filing is not available at As-of, or if the Section is missing from either Filing.
- [ ] The diff logic is a module the batch feature job (ticket 11) can call directly.
- [ ] Tests through the tool, on the fixture Universe:
  - known added and removed paragraphs are reported;
  - identical Sections score 1.0;
  - a Filing that isn't yet public is refused.
