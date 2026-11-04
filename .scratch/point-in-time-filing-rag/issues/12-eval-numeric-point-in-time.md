# 12: Eval: numeric and point-in-time sets

**What to build:** A researcher can measure number accuracy and look-ahead safety without hand labels. A numeric set is generated automatically from XBRL and scored by exact match with a tolerance. A point-in-time set is seeded from real Restatements in the Universe and fails if any later value is used.

**Blocked by:** 02 (Facts tracer: `get_financials` as-of)

**Status:** ready-for-agent

- [ ] A generator builds numeric questions (concept, Company, period, As-of) and expected values from the facts table.
- [ ] A scorer compares `get_financials` output, and later end-to-end answers, by exact match with a configurable relative tolerance.
- [ ] The point-in-time set is built by finding real Restatements (a changed value for the same period) and asking for each value at As-ofs just before and just after the restating Filing.
- [ ] Any answer that uses the restated value before it was available counts as a failure and is reported by name.
- [ ] Runs as an evaluation-harness command, not as part of pytest.
