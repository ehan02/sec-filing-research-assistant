# 11: Batch feature job

**What to build:** A quant runs one command over the Universe and gets `features.parquet`: one row per Company × Original 10-K, dated by that Filing's Availability Time and computed only from Filings public at that moment. The file is ready to join with forward returns elsewhere.

**Blocked by:** 07 (`section_diff` tool)

**Status:** done

- [x] For each Original 10-K, the job compares Item 1A and Item 7 with the prior Original 10-K available at this Filing's own Availability Time, using the Section Diff module.
- [x] Each row also records the change in risk-factor count and the length of each Section.
- [x] Output is keyed by CIK, accession number and Availability Time. A Filing with no prior 10-K gets null similarity, not a skipped row.
- [x] Re-running the job produces identical output.
- [x] A test on the fixture Universe checks that the prior-year comparison never uses a Filing accepted after the row's Availability Time.

## Comments

**Done (2026-11-04).**
- **Command:** `python -m src.features.filing_features` writes `data/features.parquet` for every Company with saved Filings. `build_features(downloader)` returns the same table as a DataFrame.
- **Rows:** one per Original 10-K (`form == "10-K"`; 10-K/A rows are excluded), ordered by CIK and Availability Time. Columns: `cik, ticker, accession_no, availability_time, fiscal_year, prior_accession_no, item_1a_similarity, item_1a_words, item_7_similarity, item_7_words, risk_factor_count, risk_factor_count_change`.
- **Point-in-time prior:** the previous Original 10-K by Availability Time, so it was always public before the row's Filing. A 10-K with no earlier one gets nulls for `prior_accession_no`, the similarities and the count change, not a skipped row. The similarity is `diff_paragraphs` from the Section Diff module, the same score `section_diff` returns.
- **Risk-factor count:** a new Glossary term. The parser now flags each text block as `emphasized` when all of its text is bold or italic (by tag or inline style). A Risk Factor is an emphasized Item 1A paragraph ending in a period, which skips category headings. The fixture 10-Ks' risk sentences are now bold, with a bold "Business Risks" category heading; the text is unchanged.
- **Determinism:** a test writes the file twice and checks that the bytes are identical.
- **Real AAPL run** (5 Original 10-Ks, FY2022–FY2026): FY2022 has no prior because only filings since 2022 are downloaded. Item 1A similarity is 0.995–0.999, and Item 7 is 0.945–0.964. Risk factors: 29, 28, 28, 27, 28; FY2024's 28 matches a hand count of its bold-italic headings. Item 1A grew from 9,780 to 12,330 words in FY2026.
