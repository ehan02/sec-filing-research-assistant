# 12: Eval: numeric and point-in-time sets

**What to build:** A researcher can measure number accuracy and look-ahead safety without hand labels. A numeric set is generated automatically from XBRL and scored by exact match with a tolerance. A point-in-time set is seeded from real Restatements in the Universe and fails if any later value is used.

**Blocked by:** 02 (Facts tracer: `get_financials` as-of)

**Status:** ready-for-agent

- [x] A generator builds numeric questions (concept, Company, period, As-of) and expected values from the facts table.
- [x] A scorer compares `get_financials` output, and later end-to-end answers, by exact match with a configurable relative tolerance.
- [x] The point-in-time set is built by finding real Restatements (a changed value for the same period) and asking for each value at As-ofs just before and just after the restating Filing.
- [x] Any answer that uses the restated value before it was available counts as a failure and is reported by name.
- [x] Runs as an evaluation-harness command, not as part of pytest.

## Comments

**Done (2026-11-04).**
- **Commands:** `python -m tests.eval_filings numeric [--tolerance 0.001]` and `python -m tests.eval_filings point-in-time`. Each writes `data/eval/<set>-<label>.json`.
- **Numeric set** (`numeric_set`): for a headline concept list (`NUMERIC_CONCEPTS`: revenue (both tags), gross profit, operating income, net income, diluted EPS, assets, equity), one question per Company, concept and period: the value as first reported, asked As-of that Filing's Availability Time.
- **Point-in-time set** (`point_in_time_set`): every real Restatement in the facts table (`fact_history` with more than one value). The prior value is asked 1 second before the restating Filing's Availability Time, and the restated value is asked at it.
- **Scorer:** `matches(expected, actual, tolerance)` uses a relative tolerance (default 0, exact). Both runners take a `lookup(question) -> value`, which is `financials_lookup` (`get_financials`) for now, so ticket 13 can plug in end-to-end answers. A "before" answer equal to the restated value is listed under `leaks` and printed with `LEAK` and its name.
- **Ambiguous periods are skipped.** The first real run had 8 false failures. In each, one Filing reports two values that both map to the same concept and Fiscal Period (e.g. AAPL's 35% and 21% statutory tax rates for FY2018 Q1, and two buyback authorizations in FY2019 Q2), and every later Filing repeats both, so the history looks like Restatements. Both sets now leave out any concept-period where one Filing reports two values; the fixture has a case for this.
- **Real AAPL run:** numeric 531/531 exact; point-in-time 738/738 (369 Restatements, mostly per-share values and share counts restated across years), 0 leaks. About 20 s each.
- **Found, not fixed:** for those ambiguous periods, `get_financials` itself returns whichever of the two values SQLite happens to pick. Telling them apart needs the period dates (duration vs instant) in the lookup.
