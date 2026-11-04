# 05: 10-Q, 8-K exhibits and Amendments in search

**What to build:** A researcher can search and cite 10-Q Sections by Part and Item, 8-K earnings releases by exhibit, and Amendments as their own Filings. Asking for "the latest 10-K" resolves to the latest Original available at As-of, never to an Amendment.

**Blocked by:** 04 (Hybrid retrieval: semantic + BM25 + RRF + cross-encoder)

**Status:** ready-for-agent

- [x] 10-Q Sections carry their Part (`Part I Item 2`, `Part II Item 1A`, …), so the two Item 2s are never confused.
- [x] Each 8-K Exhibit 99 document becomes one `Ex-99.x` Section, and its Chunks' URL points to the exhibit document, not the primary document.
- [x] Amendments are parsed and indexed as their own Filings and never replace their Original's Chunks.
- [x] `filing_search` can resolve "latest" for a form to the latest Original available at As-of. An Amendment is only returned when asked for by form (e.g. `10-K/A`) or by accession number.
- [x] Tests through `filing_search`:
  - a Part II Item 1A query never returns Part I Item 2;
  - an after-hours Ex-99.1 is returned at an As-of after its acceptance time and not one minute before;
  - a Part III-only 10-K/A does not displace the latest Original 10-K.

## Comments

**Done (2026-11-04).**
- **Sections kept:** an Original 10-K keeps the six spec Items. A 10-Q keeps every Item, qualified by its Part. An Amendment keeps every Item it contains, since it only holds what it amends; the fixture's Part III-only 10-K/A yields `Item 10` and `Item 11`.
- **8-Ks:** only the Exhibit 99 documents are indexed. The 8-K body just points at them, and an 8-K without an exhibit yields no Chunks and no warning.
- **Exhibit fields:** `fiscal_year` is the fiscal year of the event date (so a Q4 FY2024 release filed after year end is FY2025), and `fiscal_period` is None. Exhibit Citations carry no FY anyway.
- **Search:** `form` matches exactly, so `10-K` never returns a `10-K/A`. New `latest=True` searches only the most recent Filing of that form available at As-of, and new `accession_no` searches one Filing.
- **Real AAPL check:** 2,286 Chunks from 42 Filings (5 10-Ks, 15 10-Qs, 22 8-Ks with exhibits) took 19 min on CPU. The 20 Filings with no Chunks are all exhibit-less 8-Ks, including the 8-K/A.
  - 10-Q Sections are Part-qualified, and their periods run FY2022–FY2026, Q1–Q3.
  - "Latest 10-Q" is FY2026 Q3.
  - The 2026-11-02 Ex-99.1 is absent at 16:30:22 ET and returned at 16:30:23, its acceptance second.
