# 07: `section_diff` tool

**What to build:** An analyst asks what changed in a Company's Section between two Fiscal Years. They get a similarity score, the paragraphs added and removed, and a Citation for each Filing. Both Filings must be public at the As-of.

**Blocked by:** 03 (Text tracer: `filing_search` over 10-K Sections (BM25))

**Status:** ready-for-agent

- [x] `section_diff(ticker, section, form, fiscal_year_a, fiscal_year_b, as_of)` resolves the Ticker to a CIK and each Fiscal Year to the Original Filing of that form. An Amendment is used only if named explicitly.
- [x] It returns a similarity score, the added and removed paragraphs, and both Filings' Citations.
- [x] It fails with a clear error if either Filing is not available at As-of, or if the Section is missing from either Filing.
- [x] The diff logic is a module the batch feature job (ticket 11) can call directly.
- [x] Tests through the tool, on the fixture Universe:
  - known added and removed paragraphs are reported;
  - identical Sections score 1.0;
  - a Filing that isn't yet public is refused.

## Comments

**Done (2026-11-04).**
- **Reusable logic** lives in the diff module, for ticket 11. One function reads a Section's paragraphs from a saved Filing; another diffs two paragraph lists.
- **Similarity** is the Lazy Prices cosine of word counts, kept faithful to the paper (decided). On real AAPL Item 1A it sits in a narrow band, 0.995–0.999, but still ranks filings.
- **Reworded paragraphs** (decided): an added paragraph with at least 80% word overlap with a removed one is reported in a `changed` list of `(old, new)` pairs, not as one added plus one removed.
  - Real AAPL Item 1A, FY2022→23: 5 added, 12 removed, 43 reworded. Before pairing it was 48 added and 55 removed.
  - FY2025→26: 47 added, 28 removed, 50 reworded, including the new tariff and compute-capacity risks.
- **One Filing per side:** a Fiscal Year must resolve to exactly one Filing of the form, so a 10-Q FY (three quarters) is refused with a clear error. It's built for 10-K year-over-year comparisons.
- **As-of:** on real data, FY2025→26 as of 2026-11-02 is refused, because the FY2026 10-K wasn't accepted until 2026-11-03 08:05 ET.
