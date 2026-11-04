# Spec: Point-in-time filing research assistant

Status: ready-for-agent

## Problem Statement

An analyst or quant researching a Company's SEC filings has to open long 10-K, 10-Q and 8-K documents by hand, find the right Section, check the numbers against the financial statements, and remember which version of a number was public on a given date. General-purpose chat assistants answer from memory, make up figures, can't say which Filing a claim came from, and freely use information that was published after the date the user is asking about. That makes their answers unusable for research and look-ahead-biased for backtests.

## Solution

A local assistant over a fixed Universe of Companies. It downloads Filings and XBRL Facts from EDGAR, splits Filings into Sections and Chunks, and answers questions through three tools: narrative search, financial Facts, and Section Diffs. Every answer:

- cites the exact Filing (by accession number) and Section, or the Fact, behind each claim;
- uses only Filings and Facts whose Availability Time is at or before the question's As-of;
- takes numbers from XBRL Facts and Python arithmetic, never from the language model;
- abstains when the available Filings don't contain the answer.

A batch job produces the same point-in-time Section Diff measures as dated features for a whole Universe.

## User Stories

### Corpus

1. As a researcher, I want to download every 10-K, 10-Q and 8-K (with its Exhibit 99 documents) for a list of Tickers over a date window, so that I have a local corpus to research.
2. As a researcher, I want Amendments (10-K/A, 10-Q/A, 8-K/A) downloaded too, so that corrections and restatements are visible.
3. As a researcher, I want re-running a download to skip Filings already saved, so that I can extend or resume a Universe cheaply.
4. As a researcher, I want a download that was cut off partway to be fetched again on the next run, so that a crash never leaves a corrupt Filing in the corpus.
5. As a researcher, I want one failing Company or Filing reported and skipped, so that a long Universe download isn't lost.
6. As a researcher, I want the tool to refuse to run without a real SEC User-Agent, so that I don't get blocked by EDGAR.
7. As a researcher, I want XBRL companyfacts downloaded for each Company, so that financial questions can be answered from reported values.
8. As a researcher, I want Companies identified by CIK even though I type Tickers, so that a ticker change (FB → META) doesn't split or lose a Company's history.

### Parsing and indexing

9. As a researcher, I want each 10-K split into its Items (1, 1A, 7, 7A, 8, 9A), so that I can ask about one Section.
10. As a researcher, I want each 10-Q split into Part-qualified Sections (e.g. Part I Item 2, Part II Item 1A), so that 10-Q MD&A and 10-Q risk factors are never confused.
11. As a researcher, I want 8-K Exhibit 99 documents treated as their own Sections (e.g. Ex-99.1), so that earnings releases are searchable and citable.
12. As a researcher, I want the table of contents skipped, so that searches don't return TOC lines that merely mention a Section.
13. As a researcher, I want tables converted to markdown and kept whole with their caption, so that a retrieved table is readable and complete.
14. As a researcher, I want Chunks never to cross a Section boundary, so that every Chunk has exactly one Section to cite.
15. As a researcher, I want each Chunk to carry its Filing's accession number, form, Fiscal Year, Fiscal Period, Section, Availability Time and source document URL, so that it can be filtered and cited.
16. As a researcher, I want re-indexing a Filing to replace its Chunks rather than duplicate them, so that the index stays consistent as I fix the parser.
17. As a researcher, I want an Amendment indexed as its own Filing, so that an amended Section can be cited as the Amendment and the Original stays searchable.

### Facts

18. As a researcher, I want every XBRL Fact loaded with the accession number of the Filing that reported it, so that every number can be cited.
19. As a researcher, I want each Fact's Fiscal Year and Fiscal Period to describe the period the value covers, so that asking for FY2022 never returns a FY2022 10-K's comparatives mislabeled as another year.
20. As a researcher, I want each Fact to carry the Availability Time of its Filing, so that numbers obey the same As-of rule as text.
21. As a quant, I want asking for a value As-of a date to return the latest value available at that date, so that later Restatements never leak into a backtest.
22. As a quant, I want to see when a value was restated, so that I can tell a Restatement from a repeated comparative.

### Asking questions

23. As an analyst, I want to ask a narrative question about a Company ("what does NVDA say about export restrictions?") and get an answer with Citations, so that I can verify every claim.
24. As an analyst, I want to narrow a search by Company, form, Fiscal Year and Section, so that I can target one Filing's risk factors.
25. As an analyst, I want "the latest 10-K" to mean the latest Original 10-K available at As-of, so that a Part III-only 10-K/A doesn't hijack the question.
26. As an analyst, I want financial questions (revenue, margin, share count) answered from Facts with the arithmetic done in code, so that the numbers are exact.
27. As an analyst, I want every number in an answer cited to the Fact and Filing it came from, so that I can trace it back.
28. As an analyst, I want to ask what changed in a Section between two years and get the added and removed paragraphs with Citations, so that I can review new risks quickly.
29. As an analyst, I want combined questions (numbers plus narrative) answered as one explanation, so that I don't have to ask twice.
30. As an analyst, I want questions about a Universe ("did any company report a material weakness?") answered across all Companies, so that I can screen.
31. As an analyst, I want the assistant to abstain with "The filings provided do not contain this information." when the answer isn't there, so that I'm never given a guess as a fact.
32. As an analyst, I want questions about the future (e.g. FY2027 guidance not in any Filing) to abstain, so that the assistant never extrapolates.
33. As a researcher, I want to ask any question As-of a past date or datetime, so that I see only what was public then.
34. As a researcher, I want a date-only As-of to include Filings accepted any time that day (US Eastern), so that the rule is predictable.
35. As a researcher, I want an after-hours 8-K counted as available at its acceptance time, not the next day's filing date, so that event timing is exact.
36. As a researcher, I want an answer rejected and regenerated whenever it cites something that wasn't retrieved, so that every Citation I see is real.
37. As a researcher, I want filing text treated as data and never as instructions, so that text inside a Filing can't steer the assistant.
38. As a researcher, I want to choose between a local Ollama model and Claude, so that I can work offline or compare quality.

### Features and evaluation

39. As a quant, I want, for every Company × Filing, the year-over-year similarity of Item 1A and Item 7, the change in risk-factor count, and Section lengths, so that I can test Lazy Prices–style signals.
40. As a quant, I want those features keyed by CIK, accession number and Availability Time, so that I can join them to forward returns without look-ahead.
41. As a quant, I want each feature row computed only from Filings available at that Filing's own Availability Time, so that the prior-year comparison is point-in-time too.
42. As a quant, I want a Universe ranked by Item 1A similarity as of each Filing's Availability Time, so that I can build a cross-sectional signal.
43. As a researcher, I want a numeric eval set generated automatically from XBRL and scored by exact match with a tolerance, so that number accuracy is measured without hand labels.
44. As a researcher, I want a narrative eval set of 15–20 hand-labeled questions scored by Recall@5, citation validity and faithfulness, so that retrieval changes are measured.
45. As a researcher, I want a point-in-time eval set seeded from real Restatements, so that any leak of later values fails loudly.
46. As a researcher, I want an Abstention eval set scored by correct-decline rate, so that I know the assistant declines when it should.
47. As a researcher, I want to run the same eval sets against Ollama vs Claude and embedding model A vs B, so that I can compare configurations on equal terms.

## Implementation Decisions

**Vocabulary** follows `GLOSSARY.md`. ADR-0001 (Availability Time) and ADR-0002 (Fiscal Year) apply throughout.

### Modules

- **EDGAR downloader** (exists). Changes:
  - Form matching includes each form's Amendment (`10-K` also selects `10-K/A`).
  - Saved Filing metadata includes the Availability Time, parsed from `acceptanceDateTime` and converted to US Eastern, alongside the existing raw fields.
  - The downloader exposes a lookup from accession number to Availability Time, built from the cached submissions lists, for the facts loader to use.
- **Section parser.** Input: one saved Filing. Output: an ordered list of Sections, each with a form-aware Section ID, text, tables as markdown with captions, and its source document URL. 10-K Sections: Items 1, 1A, 7, 7A, 8, 9A. 10-Q Sections are Part-qualified: Part I Item 2, Part II Item 1A, and others where present. 8-K exhibits each become one `Ex-99.x` Section. The table of contents is detected and dropped. A Filing whose Sections can't be found yields an empty list plus a warning, never a guessed split.
- **Chunker / indexer.** Splits Sections into Chunks of 300 words (about 360 tokens) with 50 words of overlap, under the 512-token limit of the embedder and cross-encoder. (The spec first said ~800 tokens; ticket 04 found that the models never saw the last ~30% of such chunks.) Chunks never cross a Section boundary, and a table plus its caption is always a single Chunk. Writes the same Chunk IDs to Chroma (collection `filings`) and BM25. Re-indexing replaces all Chunks for an accession number.
- **Chunk metadata** (supersedes the README schema): `chunk_id, cik, ticker, company, form, is_amendment, fiscal_year, fiscal_period, report_date, availability_time, accession_no, section, chunk_idx, is_table, url`. `section` replaces `item` and holds the Section ID. `url` is the URL of the document the text came from (primary document or exhibit). `ticker` is today's Ticker, for display only. `fiscal_year`/`fiscal_period` describe the period the Filing reports on.
- **Facts loader.** Loads companyfacts into the SQLite `facts` table: `cik, concept, unit, value, period_start, period_end, fiscal_year, fiscal_period, form, accn, availability_time`.
  - `fiscal_year`/`fiscal_period` are derived from the period dates and the Company's fiscal year end, never copied from raw `fy`/`fp` (ADR-0002).
  - `availability_time` comes from the Filing named by `accn` (ADR-0001). A Fact whose `accn` has no known Availability Time is skipped and counted in a load report.
  - The Ticker is not stored. It is resolved from the CIK at display time.
- **Point-in-time fact lookup.** `get_fact(cik, concept, period, as_of)` returns the value with the latest Availability Time ≤ As-of, together with its accession number. A companion query lists every distinct value reported for (cik, concept, unit, period) over time, which is the basis for finding Restatements.
- **As-of handling.** One shared function normalizes user input to an Eastern-time datetime (date-only → 23:59:59.999 ET that day). Every tool, the retriever and the feature job filter with it. No other module interprets As-of strings.
- **Retriever.** Metadata filter (including `availability_time ≤ as_of`) → semantic top 20 + BM25 top 20 → reciprocal rank fusion (k=60) → cross-encoder (`ms-marco-MiniLM-L-6-v2` by default; `bge-reranker-base` doesn't fit in memory on an 8 GB laptop, and is selectable by config) → top 5. Embeddings: `bge-base-en-v1.5`. Retrieval runs without any LLM.
- **Section Diff.** Input: Company, Section, two Filings of the same form, As-of. Both Filings must be available at As-of, or the call fails with a clear error. "Latest" and "prior year" resolve to Originals unless an Amendment is named explicitly. Output: similarity score, added and removed paragraphs, and a Citation for each side.

### Tool contracts (agent-facing)

| Tool | Input | Output |
|---|---|---|
| `filing_search` | query, ticker?, form?, fiscal_year?, section?, as_of | Top 5 Chunks with Citation fields |
| `get_financials` | ticker, concepts, periods (Fiscal Year/Fiscal Period), as_of | Values, each with its accession number and Availability Time |
| `section_diff` | ticker, section, fiscal_year_a, fiscal_year_b, form, as_of | Similarity, added/removed paragraphs, Citations |

All three tools resolve the Ticker to a CIK on input and take a required `as_of`. An omitted As-of means "now", made explicit by the agent before the call.

### Router / agent

LangGraph router: narrative → `filing_search`, numeric → `get_financials` then Python arithmetic, change → `section_diff`, combined → numbers + narrative, nothing found → Abstention. The same rules are mirrored in the `filing-research` skill file, whose citation format needs updating to the Section-based format below.

### Generation

- The chat model is an injected dependency (Ollama or Claude, picked by config), which also gives tests a seam for a fake model.
- The prompt wraps context in `<documents>` tags marked as data, requires a Citation for every claim, and specifies the Abstention sentence.
- The language model receives numbers computed in Python and never performs arithmetic.
- Post-check: every Citation in the answer must match a retrieved Chunk or a returned Fact. A failing answer is regenerated a bounded number of times, then replaced by an Abstention.

### Citation formats

- Chunk: `[AAPL 10-K FY2024 Item 1A, 0000320193-24-000123]`; for a 10-Q `[JPM 10-Q FY2024 Q2 Part I Item 2, <accession>]`; for an exhibit `[AAPL 8-K Ex-99.1, <accession>]`; for an Amendment the form reads `10-K/A`.
- Fact: `[AAPL us-gaap:Revenues FY2022, 0000320193-24-000123]`. Fiscal Year here is the period's, and the accession number is the reporting Filing's.

### Batch feature job

For each Company × Original 10-K, compares Item 1A and Item 7 with the prior Original 10-K available at that Filing's own Availability Time, and computes the change in risk-factor count and Section lengths. Writes `features.parquet` keyed by `(cik, accession_no, availability_time)`. It uses the same Section Diff module as the tool.

## Testing Decisions

- **Good tests exercise external behavior only:** what a tool returns for a question over a known corpus, not how the parser or indexer works inside. Tests must survive a rewrite of the chunker or retriever internals.
- **Seam 1: EDGAR HTTP (existing).** Tests build a small fixture Universe by sending canned EDGAR responses through the real downloader → parser → indexer → facts loader. They use the same URL-routing HTTP fake that the downloader tests use. Fixtures are small hand-written HTML Filings and companyfacts JSON designed to hit the edge cases:
  - a 10-K with a table of contents and a table spanning a Chunk-size boundary;
  - a 10-Q with both Part I Item 2 and Part II Item 1A;
  - an 8-K with Ex-99.1 accepted after 17:30 ET;
  - a Part III-only 10-K/A;
  - a Fact repeated as an identical comparative, and a Fact restated with a different value;
  - a Fact whose period's Fiscal Year differs from the reporting Filing's.
- **Top of seam 1:** the three agent tools, called directly. Assertions are about which Chunks/Facts come back, their Citations, and what is excluded at a given As-of. Key cases:
  - an As-of one minute before vs one minute after an acceptance time;
  - date-only As-of on the acceptance day;
  - a Restatement not visible before its Filing;
  - FY2022 revenue requested from a corpus where it was also reported in a FY2024 10-K;
  - "latest 10-K" with a newer 10-K/A present;
  - Section Diff refusing a Filing that isn't yet available at As-of;
  - Ticker input resolving to CIK.
- **Seam 2: injected chat model.** Answer generation is tested with a fake model that returns scripted answers:
  - an answer citing an unretrieved accession number is rejected and regenerated;
  - repeated failures end in the exact Abstention sentence;
  - context is wrapped in `<documents>` tags;
  - numbers passed to the model come from Python.
- **No per-module unit tests** for the parser, chunker, retriever internals or `get_fact`. They are covered through the tools.
- **Real-model quality** (Ollama, Claude, embedding comparisons) is measured only by the evaluation harness (numeric, narrative, point-in-time, Abstention sets), not by pytest.
- **Prior art:** the downloader tests, which run fully offline. They use a URL-suffix-routed fake HTTP client, `tmp_path` data directories, and assertions on returned records and files rather than internals.

## Out of Scope

- Historical Tickers and a point-in-time Universe (survivorship bias); the Universe is a fixed list of today's Companies.
- 20-F / 40-F, IR PDFs, news, earnings call transcripts, 13F holdings.
- Price data, forward returns and backtesting itself; features are only produced for joining elsewhere.
- Multimodal parsing (charts, images), ESG fine-tuning.
- Real-time or streaming updates.
- Evidence that any feature has predictive value; the 10–20 Company Universe only demonstrates the pipeline.

## Further Notes

- The README says "Nothing is implemented yet", but the EDGAR downloader and its tests exist. The README also still shows `item` (not `section`), `fy`/`fp` and `filed` in its schemas and lists `section_diff` without As-of. It should be updated to match this spec and `GLOSSARY.md`.
- The submissions API's `acceptanceDateTime` (`…Z`) was checked against EDGAR index pages for two after-hours AAPL 8-Ks, one in standard time and one in daylight time. The `Z` is genuine UTC; details are in ADR-0001.
- Deriving Fiscal Year from period dates needs each Company's fiscal year end. The submissions API provides `fiscalYearEnd`; 52/53-week fiscal years (e.g. AAPL) need a tolerance of a few days.
- Grilling was cut short after round 1. Branches not yet visited include the eval set construction details, the exact regenerate-retry count, and how Universe-wide questions are fanned out by the router.
