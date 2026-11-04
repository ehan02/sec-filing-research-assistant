# 03: Text tracer: `filing_search` over 10-K Sections (BM25)

**What to build:** A researcher searches a Company's 10-Ks with `filing_search` and gets the top Chunks, each with full citation fields. Only Filings available at As-of are searched. This is the narrowest end-to-end text path: parse 10-K Sections, chunk them, index them with BM25, retrieve with metadata and As-of filtering. Semantic search comes in ticket 04.

**Blocked by:** 01 (Downloader: amendments, Availability Time, fixture Universe)

**Status:** done

- [x] A saved 10-K splits into Sections `Item 1`, `1A`, `7`, `7A`, `8`, `9A`. The table of contents is skipped. A Filing whose Sections can't be found yields no Sections plus a warning, never a guessed split.
- [x] Tables become markdown, and each table with its caption is exactly one Chunk.
- [x] Chunks are about 800 tokens with 100 overlap and never cross a Section boundary.
- [x] Each Chunk carries the spec's metadata: CIK, Ticker (display only), company, form, is_amendment, Fiscal Year, Fiscal Period, report date, Availability Time, accession number, Section, chunk index, is_table, and source URL.
- [x] Indexing is keyed by accession number, and re-indexing a Filing replaces its Chunks rather than duplicating them.
- [x] `filing_search(query, ticker?, form?, fiscal_year?, section?, as_of)` applies the metadata filter, including Availability Time at or before As-of, then BM25, and returns the top 5 Chunks with citation fields.
- [x] Tests through the tool, on the fixture Universe:
  - a 10-K not yet public at As-of is never returned;
  - a table spanning the chunk-size boundary comes back whole;
  - table-of-contents lines are not returned;
  - a Section filter limits results to that Section.

## Comments

**Done (2026-11-04).**
- Chunks are stored in a SQLite `chunks` table, so the metadata and As-of filter is plain SQL and BM25 runs over whatever survives. Ticket 04 adds Chroma under the same chunk IDs.
- Chunk size is counted in words: 600 words with 75 overlap, roughly 800 and 100 tokens. Ticket 04 later cut this to 300 words with 50 overlap, to fit the models' 512-token limit.
- Only chunks that share a query term are returned. BM25 scores can be zero or negative for a real match when every filtered chunk contains the term, so the score can't be the cutoff.
- In table markdown, EDGAR's separate `$`, `%` and `(` cells are merged into their numbers, and the header row is padded for the empty corner cell.
- Checked on the five real AAPL 10-Ks (FY2022–FY2026): all six Sections found in each, with sensible sizes, starting text and table captions.
- Filings downloaded before ticket 01 lack `availability_time` in their metadata and can't be indexed until they're re-downloaded with `--refresh`.
