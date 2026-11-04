# 04: Hybrid retrieval: semantic + BM25 + RRF + cross-encoder

**What to build:** `filing_search` finds relevant Chunks even when the question's wording differs from the filing's. The same Chunks are embedded into Chroma alongside BM25. Retrieval runs the full pipeline: metadata and As-of filter, then semantic top 20 plus BM25 top 20, merged with reciprocal rank fusion (k=60), reranked by the cross-encoder, returning the top 5. The tool's contract does not change.

**Blocked by:** 03 (Text tracer: `filing_search` over 10-K Sections (BM25))

**Status:** done

- [x] Chunks are embedded with `bge-base-en-v1.5` into the Chroma `filings` collection under the same chunk IDs as BM25. Re-indexing by accession number replaces them in both indexes.
- [x] The As-of and metadata filter applies before both the semantic and BM25 searches. A Chunk past As-of can never re-enter through fusion.
- [x] Reciprocal rank fusion (k=60) merges the two result lists, `bge-reranker-base` reorders the merged list, and the top 5 are returned.
- [x] Embedding and reranker models are configurable, so ticket 13 can compare model A against model B.
- [x] Tests through `filing_search`:
  - a paraphrased query that shares no keywords with the text still finds the right Chunk;
  - As-of exclusion holds with both retrievers on.
  - Tests may use small or stubbed models so they stay fast and offline.

## Comments

**Done (2026-11-04), with one deviation from the spec.**
- **Reranker:** the default is `cross-encoder/ms-marco-MiniLM-L-6-v2`, not `BAAI/bge-reranker-base`. bge-reranker-base hit `MemoryError` while loading on this 7.7 GB machine with everyday apps open, and it would also add seconds per query on CPU. It stays selectable via `RERANK_MODEL`, and the embedder via `EMBED_MODEL`.
- **As-of gate:** the SQL metadata and As-of filter is the only gate. Semantic similarity is computed over the surviving Chunks' stored Chroma embeddings, so nothing past As-of can come back through fusion.
- **Chroma location:** the `chroma` folder beside the chunks database.
- **Tests:** they use the real models and run offline once the models are cached. The suite takes about 35 s.
- **Chunk size changed (approved):** both models truncate input at 512 tokens. The original 600-word chunks were 700–740 tokens, so about the last 30% of each chunk was invisible to semantic search and reranking. Example: the "single or limited sources" passage at word 437 of 600 in FY2024 Item 1A was missed.
  - 350 words still left 4 of 486 text chunks over 512 tokens, so chunks are now 300 words with 50 overlap.
  - On the AAPL 10-Ks that gives a median of 361 tokens and a maximum of 502.
  - 20 of 218 whole-table chunks still exceed 512; the models see their caption, header and first rows.
- **Real AAPL check:** 774 chunks embedded in 316 s on CPU. Queries take 0.7–4.5 s.
  - Single-source suppliers: the top hit is now the FY2023 Item 1A passage.
  - China trade risk: Item 1A for each year.
  - Internal controls: the exact "management has concluded … effective" sentence in Item 9A.
  - iPhone revenue: the net-sales-by-category tables.
