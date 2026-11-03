# SEC Filing Research Assistant

> Ask questions about 10-K, 10-Q and 8-K filings with cited answers and point-in-time filtering. Runs locally with Ollama, ChromaDB and LangGraph.

**Status:** design phase. Nothing is implemented yet; see [Roadmap](#roadmap).

---

## Purpose

A local, point-in-time research assistant over SEC filings with two modes:

- **Analyst / PM mode.** Answers questions about a company's filings and cites the exact filing and section.
  *"What did NVDA say about export restrictions in its latest 10-K, and how did that change from last year?"*
- **Quant mode.** Extracts text features across a universe of companies, dated by filing date, for use in backtests.
  *"For all 50 companies, score how much Item 1A changed year over year."* (In the style of Cohen, Malloy & Nguyen, 2020, "Lazy Prices".)

**Rules it follows:** every number traces to an XBRL fact, every claim traces to a filing section, and nothing is used before its filing date.

---

## Scope

| In | Out |
|---|---|
| 10-K, 10-Q, 8-K Exhibit 99.1 (earnings releases) | Academic papers, news, earnings call transcripts |
| XBRL company facts (financial-statement numbers) | 13F holdings (possible later extension) |
| Optional: 20-F / 40-F, manually downloaded IR PDFs | ESG fine-tuning, multimodal parsing |
| A universe of 10–20 companies × 3–5 years to start | Real-time data; price data inside the RAG |

---

## Tech stack (all local)

| Layer | Tool |
|---|---|
| Language / models | Python 3.12, Pydantic |
| Agent | LangGraph + LangChain |
| LLM | Ollama (`qwen2.5:7b` or `llama3.1:8b`); Claude API for comparison |
| Embeddings | sentence-transformers `BAAI/bge-base-en-v1.5` |
| Re-ranker | `CrossEncoder("BAAI/bge-reranker-base")` |
| Vector store | ChromaDB, collection `filings` |
| Keyword index | `rank-bm25` |
| Numbers store | SQLite, table `facts` |
| Parsing | `requests`, `beautifulsoup4`, `lxml`; `pypdf` as a fallback for PDFs |

---

## Architecture

```
               EDGAR (submissions API · filing HTML · companyfacts API)
                                  │
                     [1] Downloader + cache (User-Agent, under 10 req/s)
                    ┌─────────────┴─────────────┐
           [2] Text pipeline            [3] Numbers pipeline
           HTML → Items → chunks        companyfacts → SQLite facts
           → Chroma + BM25
                    └─────────────┬─────────────┘
                     [4] Tools (all take as_of)
           filing_search · get_financials · section_diff
                                  │
                     [5] LangGraph router / agent
                                  │
                     [6] Answer generation + citation check
                                  │
                     [7] Evaluation harness  ·  [8] Batch feature job
```

---

## Components

### [1] Downloader: `src/filings/edgar.py`
- Ticker→CIK map from SEC's `company_tickers.json`.
- Reads the filing list (`form, accessionNumber, reportDate, filingDate, acceptanceDateTime, primaryDocument`) from `data.sec.gov/submissions/CIK##########.json`.
- Saves raw files under `data/filings/{cik}/{accession}/`. It's idempotent (filings already saved are skipped), stays under 10 requests per second, and sends the User-Agent that SEC requires, set from `.env`.

### [2] Text pipeline: `src/filings/parse.py`, `src/rag/index.py`
- **Parse:** strip the HTML, split into Items (1, 1A, 7, 7A, 8, 9A; Part I Item 2 for 10-Qs), and skip the table of contents.
- **Tables:** convert to markdown and keep each one in a single chunk, with its caption.
- **Chunk:** about 800 tokens with 100 overlap, never crossing an Item boundary.
- **Index:** embed into Chroma and build BM25 over the same `chunk_id`s. Re-indexing is keyed by accession number.

### [3] Numbers pipeline: `src/filings/xbrl.py`
- Loads `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` into the SQLite `facts` table.
- `get_fact(ticker, concept, period, as_of)` returns the most recent value with `filed ≤ as_of`, which handles restatements.

### [4] Tools: `src/agents/tools.py`

| Tool | Input | Output |
|---|---|---|
| `filing_search` | query, ticker?, form?, fy?, item?, as_of | Top 5 chunks with citation metadata |
| `get_financials` | ticker, concepts, periods, as_of | A table of values, each with its accession number |
| `section_diff` | ticker, item, fy_a, fy_b | Similarity score, added and removed paragraphs, citations |

**Retrieval inside `filing_search`:** metadata filter first → semantic top 20 + BM25 top 20 → reciprocal rank fusion (k=60) → cross-encoder → top 5.

### [5] Router / agent: `src/agents/`, `skills/filing-research/SKILL.md`

| Question type | Route |
|---|---|
| Narrative ("what does X say about…") | `filing_search` |
| Numeric ("revenue, margin, share count…") | `get_financials` → Python math |
| Change ("what's new vs last year") | `section_diff` |
| Combined | Numbers + narrative, explained together |
| Not in the filings | Abstain |

### [6] Generation: `src/rag/answer.py`
- A citation prompt: use only the given context, cite every claim, otherwise reply *"The filings provided do not contain this information."*
- Context is wrapped in `<documents>` tags marked as data, never instructions.
- **The LLM does no arithmetic:** numbers come from tools and Python, and the LLM only explains them.
- **Post-check:** every citation must match a retrieved chunk or fact, or the answer is rejected and regenerated.

### [7] Evaluation: `tests/eval_filings.py`

| Set | How it's made | Metric |
|---|---|---|
| Numeric | Generated automatically from XBRL | Exact match (with tolerance) |
| Narrative | 15–20 hand-labeled questions | Recall@5, citation validity, faithfulness |
| Point-in-time | as_of queries spanning restatements | Must not use later values |
| Abstention | Questions with no answer in the filings | Correct-decline rate |

You also compare Ollama vs Claude and embedding model A vs B on the same sets.

### [8] Batch feature job: `src/features/filing_features.py`
- For each ticker × filing: Item 1A / Item 7 year-over-year similarity, change in risk-factor count, and section lengths.
- Output: `features.parquet` keyed by `(cik, accession, filed_date)`, ready to join with forward returns elsewhere.
- A 10–20 company universe demonstrates the pipeline. It is not evidence that the signal works.

---

## Data schemas

**Chunk metadata (Chroma)**
```
chunk_id, cik, ticker, company, form, fiscal_year, fiscal_period,
report_date, filed_date, acceptance_datetime, accession_no,
item, chunk_idx, is_table, url
```

**`facts` table (SQLite)**
```
cik, ticker, concept, unit, value, period_start, period_end,
fy, fp, form, accn, filed
```

**Citation format**
```
[AAPL 10-K FY2024 Item 1A, 0000320193-24-000123]
```

---

## Example questions (also the evaluation seed set)

| # | Question | Tool | How it's verified |
|---|---|---|---|
| 1 | What are the top new risk factors in MSFT's FY2024 10-K that weren't in FY2023? | `section_diff` (Item 1A) | Read both Items |
| 2 | What were AAPL's revenue and gross margin each year from FY2020 to FY2024? | `get_financials` + Python | Automatic, against XBRL |
| 3 | Does NVDA disclose customer concentration? Which customers exceed 10% of revenue? | `filing_search` | Citation check |
| 4 | How did JPM describe its credit-loss outlook in the last two 10-Qs? | `filing_search` (MD&A, filtered by date) | Citation check |
| 5 | What's the change in share count and buyback authorization over 3 years? | `get_financials` + `filing_search` | Automatic + citation |
| 6 | Did any company in the universe change auditor or report a material weakness? | `filing_search` (Item 9A, all tickers) | Hand label |
| 7 | Rank the universe by Item 1A year-over-year similarity, as of each filing date | `section_diff` (batch) | Reproducible output |
| 8 | Who does TSLA list as key suppliers or single-source risks? | `filing_search` | Citation check |
| 9 | As of 2022-03-01, what was META's latest reported capex? | `get_financials` with `as_of` | Automatic; must not use later restatements |
| 10 | What's NVDA's FY2027 revenue guidance? | Should abstain | Abstention accuracy |

---

## Project layout

```
sec-filing-research-assistant/
├── src/
│   ├── filings/    edgar.py · parse.py · xbrl.py · diff.py
│   ├── rag/        index.py · retrieve.py · answer.py
│   ├── agents/     tools.py · nodes.py · agent.py
│   └── features/   filing_features.py
├── skills/filing-research/SKILL.md
├── data/
│   ├── filings/    raw EDGAR downloads (gitignored)
│   ├── chroma/     vector store (gitignored)
│   └── facts.db    XBRL facts (gitignored)
├── tests/eval_filings.py
├── requirements.txt
├── .env            SEC User-Agent, API keys (never committed)
└── README.md
```

---

## Design principles

1. **Point-in-time everywhere:** every tool filters on `filed ≤ as_of`.
2. **Identity is the accession number,** never the ticker.
3. **Structure before semantics:** split by Item and keep tables whole.
4. **Numbers from XBRL, words from RAG.** The LLM never calculates.
5. **Cite or abstain.** Citations are checked in code.
6. **Retrieval first:** get retrieval working and measured before adding the LLM.
7. **Measure every change** against the fixed evaluation sets.

---

## Roadmap

- [ ] 1. EDGAR downloader + ticker→CIK map + local cache
- [ ] 2. XBRL facts → SQLite, `get_fact(..., as_of)`
- [ ] 3. Item parser (10-K / 10-Q), tables to markdown
- [ ] 4. Chunking + Chroma + BM25 indexing
- [ ] 5. Hybrid retrieval: filters → semantic + BM25 → RRF → cross-encoder
- [ ] 6. `section_diff` tool
- [ ] 7. Generation + citation check
- [ ] 8. LangGraph router / agent + `SKILL.md`
- [ ] 9. Evaluation harness (numeric, narrative, point-in-time, abstention)
- [ ] 10. Batch feature job + demo
- [ ] Later: embedding comparison, Ollama vs Claude comparison, 13F holdings extension

---

## Setup (planned)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen2.5:7b
```

`.env`:
```
SEC_USER_AGENT=YourName your-contact@example.com
ANTHROPIC_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_LLM=ollama
```

SEC requires a descriptive User-Agent with contact details for EDGAR access. Set your own in `.env`.

---

## Relation to *Machine Learning for Trading*, Chapter 22

The design builds on Chapter 22 (RAG for Financial Research):

| Notebook | Status here |
|---|---|
| 01 SEC filing pipeline | **Rebuilt from its principles:** accession-number identity, filing-date availability, metadata. Full filings are downloaded from EDGAR instead of using the prepared corpus. |
| 02 Domain embeddings comparison | **Later experiment** on this corpus |
| 03 Hybrid retrieval | **Ported:** BM25, semantic search, RRF, cross-encoder |
| 04 RAGAS evaluation | **Adapted:** failure categories kept; grading mostly automatic against XBRL |
| 05 10-K RAG assistant | **Ported:** citation prompt, abstention, retrieve → extract → compute → narrate, moved from LlamaIndex/OpenAI to LangChain/Ollama |
| 06 ESG RAG vs fine-tune | Out of scope |
| 07 Institutional holdings graph | Out of scope (13F is a candidate extension) |
| 08 RAG security | **Lighter:** context-as-data wrapping and citation checks only |

**New in this project:** XBRL facts database, own EDGAR downloader and Item parser, 10-Q/8-K coverage, enforced as-of filtering (including restatements), section diff tool, a router across text, numbers and diffs, batch feature extraction, and local-first dual LLM providers.
