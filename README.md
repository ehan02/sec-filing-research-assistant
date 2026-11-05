# SEC Filing Research Assistant

[![CI](https://github.com/ehan02/sec-filing-research-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/ehan02/sec-filing-research-assistant/actions/workflows/ci.yml)

A local research assistant for SEC 10-K, 10-Q and 8-K filings. It gives cited answers, filters strictly by point in time, and runs on your own machine with Ollama, ChromaDB and LangGraph.

It answers questions like *"What did NVDA say about export restrictions in its latest 10-K, and how did that change from last year?"* and *"As of 2022-03-01, what was AAPL's latest reported revenue?"* Every claim in an answer cites the filing Section it came from, and every number traces back to an XBRL fact. No information is used before the moment it became public.

## Highlights

- **No look-ahead bias.** Every tool takes an `as_of` timestamp and only sees filings whose EDGAR acceptance time is at or before it ([ADR-0001](docs/adr/0001-availability-time-is-acceptance-datetime.md)). Later restatements never leak into earlier answers. This is tested against 738 real restatement questions with zero leaks.
- **Numbers come from XBRL, not the LLM.** Financials are loaded from SEC's companyfacts API into SQLite and calculated in Python. The LLM only explains values it is handed.
- **Citations are checked in code.** Every citation must match a chunk or fact that was actually retrieved. Otherwise the answer is rejected and generated again. If the filings don't contain the answer, the assistant abstains.
- **Hybrid retrieval.** Metadata filter → dense (bge-base) top 20 + BM25 top 20 → reciprocal rank fusion → cross-encoder re-rank → top 5.
- **Structure-aware parsing.** HTML is split into form-aware Sections (10-K Items, Part-qualified 10-Q Items, 8-K exhibits) with the table of contents skipped. Tables become markdown and are never split across chunks.
- **LangGraph router** sends each question to a narrative, numeric, change (`section_diff`), combined or abstain route.
- **Quant feature job.** Computes Item 1A / Item 7 year-over-year similarity and risk-factor counts for each filing, keyed by Availability Time. This follows *Lazy Prices* (Cohen, Malloy & Nguyen, 2020).
- **Evaluation harness** with numeric, narrative, point-in-time and abstention sets, plus side-by-side comparison of model configurations.

## Results

Measured on AAPL and NVDA filings (about 130 filings over 5 years):

| Eval set | Questions | Metric | Result |
|---|---|---|---|
| Numeric (generated from XBRL) | 531 | Exact-match accuracy, `get_financials` | **1.000** |
| Point-in-time (every real restatement, asked 1 s before and at availability) | 738 | Accuracy / leaks | **1.000 / 0 leaks** |
| Narrative (hand-labeled evidence) | 19 | Recall@5, `filing_search` | **0.868** |
| Abstention (unanswerable questions) | 8 | Correct-decline rate | **1.000** |

The tool layer is exact. The end-to-end answer quality depends on the model. A smoke run through the full router with the 3B `llama3.2` on a laptop (2 questions per set) got citation validity 1.0 and zero leaks. Its numeric-answer and faithfulness scores were low, which shows how much a small local model limits the result. The harness compares Ollama and Claude configurations on the same sets (`python -m tests.eval_filings compare …`).

## Architecture

```
               EDGAR (submissions API · filing HTML · companyfacts API)
                                  │
                     [1] Downloader + cache (User-Agent, under 10 req/s)
                    ┌─────────────┴─────────────┐
           [2] Text pipeline            [3] Numbers pipeline
           HTML → Sections → chunks     companyfacts → SQLite facts
           → Chroma + BM25
                    └─────────────┬─────────────┘
                     [4] Tools (all take as_of)
           filing_search · get_financials · section_diff
                                  │
                     [5] LangGraph router
                                  │
                     [6] Answer generation + citation check
                                  │
                     [7] Evaluation harness  ·  [8] Batch feature job
```

| # | Component | Code |
|---|---|---|
| 1 | EDGAR downloader: ticker→CIK, amendments, Availability Time in US Eastern, idempotent cache | `src/filings/edgar.py`, `availability.py` |
| 2 | Section parser, tables to markdown, 300-word section-bounded chunks, Chroma + BM25 index | `src/filings/parse.py`, `src/rag/index.py` |
| 3 | XBRL facts → SQLite. Fiscal year comes from each value's own period ([ADR-0002](docs/adr/0002-fiscal-year-describes-the-reported-period.md)) | `src/filings/xbrl.py` |
| 4 | Tools: `filing_search`, `get_financials`, `section_diff` | `src/agents/tools.py`, `src/rag/retrieve.py`, `src/filings/diff.py` |
| 5 | Router: plan → route node → answer | `src/agents/agent.py`, `nodes.py`, [`SKILL.md`](skills/filing-research/SKILL.md) |
| 6 | Context-only prompts, `<documents>` wrapped as data, citation post-check, abstention | `src/rag/answer.py` |
| 7 | Evaluation harness | `tests/eval_filings.py`, `tests/eval/` |
| 8 | Point-in-time feature job → `features.parquet` | `src/features/filing_features.py` |

**Citation formats**
```
[AAPL 10-K FY2024 Item 1A, 0000320193-24-000123]          10-K Section
[JPM 10-Q FY2024 Q2 Part I Item 2, <accession>]           10-Q Section
[AAPL 8-K Ex-99.1, <accession>]                           8-K exhibit
[AAPL us-gaap:Revenues FY2022, 0000320193-24-000123]      XBRL fact
```

## Tech stack

Python 3.12 · LangGraph / LangChain · Ollama (`llama3.2`) with Claude as an optional provider · sentence-transformers (`BAAI/bge-base-en-v1.5`, `ms-marco-MiniLM-L-6-v2` cross-encoder) · ChromaDB · rank-bm25 · SQLite · BeautifulSoup/lxml · pandas/pyarrow · pytest · ruff

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; use source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
ollama pull llama3.2
cp .env.example .env            # then set SEC_USER_AGENT to your name and email
```

SEC requires a descriptive User-Agent with contact details for EDGAR access.

**1. Download filings and XBRL facts**
```bash
python -m src.filings.edgar AAPL NVDA --years 5
```

**2. Build the chunk index and facts table, then ask a question**
```python
from src.agents.agent import ask
from src.agents.tools import FACTS_DB
from src.filings.edgar import EdgarClient, EdgarDownloader
from src.filings.xbrl import load_facts
from src.rag.answer import chat_model
from src.rag.index import index_company

downloader = EdgarDownloader(EdgarClient())
for ticker in ["AAPL", "NVDA"]:
    index_company(downloader, ticker)
    load_facts(downloader, ticker, FACTS_DB)

result = ask("Does NVDA disclose customer concentration?", chat_model("ollama"), as_of="2024-06-01")
print(result["answer"], result["citations"])
```

**3. Run evaluations and the feature job**
```bash
python -m tests.eval_filings numeric
python -m tests.eval_filings point-in-time
python -m tests.eval_filings narrative
python -m tests.eval_filings all --llm ollama --label ollama-bge
python -m src.features.filing_features
```

## Tests

```bash
python -m pytest -q
python -m ruff check .
```

The test suite runs offline against a fake EDGAR server and a synthetic fixture company (`tests/fixture_universe.py`). It covers amendments, restatements, as-of boundaries, section parsing, retrieval, citation rejection and every router route. The first run downloads the embedding and re-ranker models from Hugging Face.

To lint and test before every commit, enable the hook once per clone: `git config core.hooksPath .githooks`.

## Project docs

- [`GLOSSARY.md`](GLOSSARY.md): domain terms (Availability Time, Filing, Section, Restatement, …)
- [`docs/adr/`](docs/adr/): architecture decision records
- [`.scratch/point-in-time-filing-rag/`](.scratch/point-in-time-filing-rag/): the spec and the 14 implementation tickets the project was built from

## Roadmap

- [x] EDGAR downloader with amendments and Availability Time
- [x] XBRL facts with `get_financials(..., as_of)`
- [x] Hybrid `filing_search` over 10-K, 10-Q and 8-K, including amendments
- [x] Narrative retrieval eval
- [x] `section_diff` tool
- [x] Cited narrative and numeric answers
- [x] LangGraph router
- [x] Point-in-time batch feature job
- [x] Numeric, point-in-time and answer-quality evals with model comparison
- [ ] Demo run on a 10–20 company universe with a one-command pipeline ([ticket 14](.scratch/point-in-time-filing-rag/issues/14-demo-universe-run.md))
- [ ] Later: embedding model comparison, 13F holdings

The feature job shows that the pipeline works. It is not evidence that the signal predicts returns.

## Acknowledgements

The design builds on Chapter 22 (RAG for Financial Research) of *Machine Learning for Trading*. It ports that chapter's hybrid retrieval, citation prompt and abstention pattern from LlamaIndex/OpenAI to LangChain/Ollama. New in this project: its own EDGAR downloader and Section parser, an XBRL facts database, 10-Q/8-K coverage, enforced as-of filtering across restatements, `section_diff`, the router, and batch feature extraction.

## License

[MIT](LICENSE)
