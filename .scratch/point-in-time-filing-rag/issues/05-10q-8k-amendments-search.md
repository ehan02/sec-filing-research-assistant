# 05: 10-Q, 8-K exhibits and Amendments in search

**What to build:** A researcher can search and cite 10-Q Sections by Part and Item, 8-K earnings releases by exhibit, and Amendments as their own Filings. Asking for "the latest 10-K" resolves to the latest Original available at As-of, never to an Amendment.

**Blocked by:** 04 (Hybrid retrieval: semantic + BM25 + RRF + cross-encoder)

**Status:** ready-for-agent

- [ ] 10-Q Sections carry their Part (`Part I Item 2`, `Part II Item 1A`, …), so the two Item 2s are never confused.
- [ ] Each 8-K Exhibit 99 document becomes one `Ex-99.x` Section, and its Chunks' URL points to the exhibit document, not the primary document.
- [ ] Amendments are parsed and indexed as their own Filings and never replace their Original's Chunks.
- [ ] `filing_search` can resolve "latest" for a form to the latest Original available at As-of. An Amendment is only returned when asked for by form (e.g. `10-K/A`) or by accession number.
- [ ] Tests through `filing_search`:
  - a Part II Item 1A query never returns Part I Item 2;
  - an after-hours Ex-99.1 is returned at an As-of after its acceptance time and not one minute before;
  - a Part III-only 10-K/A does not displace the latest Original 10-K.
