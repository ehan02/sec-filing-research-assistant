# 11: Batch feature job

**What to build:** A quant runs one command over the Universe and gets `features.parquet`: one row per Company × Original 10-K, dated by that Filing's Availability Time and computed only from Filings public at that moment. The file is ready to join with forward returns elsewhere.

**Blocked by:** 07 (`section_diff` tool)

**Status:** ready-for-agent

- [ ] For each Original 10-K, the job compares Item 1A and Item 7 with the prior Original 10-K available at this Filing's own Availability Time, using the Section Diff module.
- [ ] Each row also records the change in risk-factor count and the length of each Section.
- [ ] Output is keyed by CIK, accession number and Availability Time. A Filing with no prior 10-K gets null similarity, not a skipped row.
- [ ] Re-running the job produces identical output.
- [ ] A test on the fixture Universe checks that the prior-year comparison never uses a Filing accepted after the row's Availability Time.
