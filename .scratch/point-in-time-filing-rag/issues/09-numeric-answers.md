# 09: Numeric answers

**What to build:** An analyst asks a financial question ("AAPL revenue and gross margin FY2020–FY2024") and gets exact numbers. They come from `get_financials`, any arithmetic is done in Python, and the model only narrates them. Every number carries a Fact Citation.

**Blocked by:** 02 (Facts tracer: `get_financials` as-of), 08 (Cited narrative answers)

**Status:** ready-for-agent

- [ ] Derived values (margins, growth, differences) are computed in Python from `get_financials` output and passed to the model as given numbers. The model never performs arithmetic.
- [ ] Fact Citations use the format `[TICKER concept FYyyyy, accession]`, with the period's Fiscal Year and the reporting Filing's accession number.
- [ ] The post-check from ticket 08 also validates Fact Citations against the Facts returned, and rejects any number in the answer that isn't among the given values.
- [ ] A missing Fact for a requested period is stated as unavailable, not estimated.
- [ ] Tests with the fake model:
  - the numbers passed to the model match Python's computation;
  - a scripted answer containing a number that wasn't given is rejected;
  - FY labels in Citations are the period's, not the Filing's.
