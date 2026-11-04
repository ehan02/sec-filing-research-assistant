# 06: Retrieval eval: narrative set, Recall@5

**What to build:** Before any LLM is involved, a researcher can measure retrieval quality. A fixed set of 15–20 hand-labeled narrative questions runs against the real index and is scored by Recall@5, so every later retrieval change is measured (design principles 6 and 7).

**Blocked by:** 05 (10-Q, 8-K exhibits and Amendments in search)

**Status:** ready-for-agent

- [ ] The narrative eval set is a versioned file: each question has a Ticker, an As-of, and the labeled relevant Section(s) or Chunk IDs. It is seeded from README example questions 1, 3, 4, 6 and 8.
- [ ] The evaluation harness runs the set through `filing_search` and reports Recall@5 per question and overall.
- [ ] The harness can run with a chosen embedding or reranker configuration and write results so runs can be compared.
- [ ] It runs as a separate command, not as part of pytest.
