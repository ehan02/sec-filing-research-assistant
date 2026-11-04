# 04: Hybrid retrieval: semantic + BM25 + RRF + cross-encoder

**What to build:** `filing_search` finds relevant Chunks even when the question's wording differs from the filing's. The same Chunks are embedded into Chroma alongside BM25. Retrieval runs the full pipeline: metadata and As-of filter, then semantic top 20 plus BM25 top 20, merged with reciprocal rank fusion (k=60), reranked by the cross-encoder, returning the top 5. The tool's contract does not change.

**Blocked by:** 03 (Text tracer: `filing_search` over 10-K Sections (BM25))

**Status:** ready-for-agent

- [ ] Chunks are embedded with `bge-base-en-v1.5` into the Chroma `filings` collection under the same chunk IDs as BM25. Re-indexing by accession number replaces them in both indexes.
- [ ] The As-of and metadata filter applies before both the semantic and BM25 searches. A Chunk past As-of can never re-enter through fusion.
- [ ] Reciprocal rank fusion (k=60) merges the two result lists, `bge-reranker-base` reorders the merged list, and the top 5 are returned.
- [ ] Embedding and reranker models are configurable, so ticket 13 can compare model A against model B.
- [ ] Tests through `filing_search`:
  - a paraphrased query that shares no keywords with the text still finds the right Chunk;
  - As-of exclusion holds with both retrievers on.
  - Tests may use small or stubbed models so they stay fast and offline.
