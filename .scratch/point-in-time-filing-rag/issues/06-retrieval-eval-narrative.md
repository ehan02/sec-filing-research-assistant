# 06: Retrieval eval: narrative set, Recall@5

**What to build:** Before any LLM is involved, a researcher can measure retrieval quality. A fixed set of 15–20 hand-labeled narrative questions runs against the real index and is scored by Recall@5, so every later retrieval change is measured (design principles 6 and 7).

**Blocked by:** 05 (10-Q, 8-K exhibits and Amendments in search)

**Status:** ready-for-agent

- [x] The narrative eval set is a versioned file: each question has a Ticker, an As-of, and the labeled relevant Section(s) or Chunk IDs. It is seeded from README example questions 1, 3, 4, 6 and 8.
- [x] The evaluation harness runs the set through `filing_search` and reports Recall@5 per question and overall.
- [x] The harness can run with a chosen embedding or reranker configuration and write results so runs can be compared.
- [x] It runs as a separate command, not as part of pytest.

## Comments

**Done (2026-11-04).**
- **Labels:** each relevant item is a Filing, a Section and an evidence phrase. A retrieved Chunk counts when it comes from that Filing and Section and contains the phrase, so labels survive re-chunking. Labels were found by searching Chunk text in SQL, not through the retriever.
- **Scope:** every question pins its As-of and the filters the router would pass. The set has 19 questions. README seeds 1, 3, 4, 6 and 8 are adapted to AAPL, the only Company downloaded; extend the set when the Universe grows.
- **Running it:** `python -m tests.eval_filings narrative [--db PATH] [--label NAME]`. Models come from `EMBED_MODEL` and `RERANK_MODEL`. Results go to `data/eval/narrative-<label>.json`, which is gitignored.
- **Baseline** (bge-base-en-v1.5 + ms-marco-MiniLM-L-6-v2, 300-word chunks): **Recall@5 = 0.868**. Three questions miss at least one item: EU Digital Markets Act 0.0, global minimum tax 0.0, effective tax rate 0.5. In each, retrieval reached the right Section but ranked other chunks of a long Item 1A or Item 8 above the passage that answers.
