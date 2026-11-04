# 03: Text tracer: `filing_search` over 10-K Sections (BM25)

**What to build:** A researcher searches a Company's 10-Ks with `filing_search` and gets the top Chunks, each with full citation fields. Only Filings available at As-of are searched. This is the narrowest end-to-end text path: parse 10-K Sections, chunk them, index them with BM25, retrieve with metadata and As-of filtering. Semantic search comes in ticket 04.

**Blocked by:** 01 (Downloader: amendments, Availability Time, fixture Universe)

**Status:** ready-for-agent

- [ ] A saved 10-K splits into Sections `Item 1`, `1A`, `7`, `7A`, `8`, `9A`. The table of contents is skipped. A Filing whose Sections can't be found yields no Sections plus a warning, never a guessed split.
- [ ] Tables become markdown, and each table with its caption is exactly one Chunk.
- [ ] Chunks are about 800 tokens with 100 overlap and never cross a Section boundary.
- [ ] Each Chunk carries the spec's metadata: CIK, Ticker (display only), company, form, is_amendment, Fiscal Year, Fiscal Period, report date, Availability Time, accession number, Section, chunk index, is_table, and source URL.
- [ ] Indexing is keyed by accession number, and re-indexing a Filing replaces its Chunks rather than duplicating them.
- [ ] `filing_search(query, ticker?, form?, fiscal_year?, section?, as_of)` applies the metadata filter, including Availability Time at or before As-of, then BM25, and returns the top 5 Chunks with citation fields.
- [ ] Tests through the tool, on the fixture Universe:
  - a 10-K not yet public at As-of is never returned;
  - a table spanning the chunk-size boundary comes back whole;
  - table-of-contents lines are not returned;
  - a Section filter limits results to that Section.
