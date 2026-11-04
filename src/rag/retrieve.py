"""Hybrid retrieval: metadata filter -> semantic + BM25 -> RRF (k=60) -> cross-encoder.

The SQL metadata and As-of filter is the only gate: semantic similarity is
computed over the surviving Chunks' stored embeddings, so a Chunk past As-of
can never re-enter through either retriever.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from functools import cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from src.filings.availability import EASTERN
from src.rag.index import collection, connect, embed

# bge-reranker-base needs ~2 GB more memory than an 8 GB laptop has free with
# everyday apps open; set RERANK_MODEL to use it where memory allows.
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
TOP_K = 5
CANDIDATES = 20
RRF_K = 60
# bge v1.5 retrieves better when queries carry this instruction.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_TOKEN = re.compile(r"\w+")


@cache
def reranker(model: str = RERANK_MODEL) -> CrossEncoder:
    return CrossEncoder(model)


def search(db_path: Path, query: str, as_of: datetime, cik: int | None = None,
           form: str | None = None, fiscal_year: int | None = None,
           section: str | None = None, k: int = TOP_K) -> list[dict]:
    """Top ``k`` Chunks for ``query`` among those available at ``as_of``."""
    filters = {"cik": cik, "form": form, "fiscal_year": fiscal_year, "section": section}
    where = ["availability_time <= ?"] + [f"{col} = ?" for col, v in filters.items() if v is not None]
    params = [as_of.astimezone(timezone.utc).isoformat()] + [v for v in filters.values() if v is not None]
    with connect(db_path) as conn:
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM chunks WHERE {' AND '.join(where)}", params)]
    if not rows:
        return []

    # BM25 scores can be <= 0 for a real match when every candidate contains the
    # term, so "shares a query term" decides what is a BM25 match, not the score.
    corpus = [_tokens(r["text"]) for r in rows]
    query_tokens = _tokens(query)
    bm25 = BM25Okapi(corpus).get_scores(query_tokens)
    keyword = [i for i, doc in enumerate(corpus) if not set(query_tokens).isdisjoint(doc)]
    keyword = sorted(keyword, key=lambda i: bm25[i], reverse=True)[:CANDIDATES]

    stored = collection(db_path).get(ids=[r["chunk_id"] for r in rows], include=["embeddings"])
    by_id = dict(zip(stored["ids"], stored["embeddings"]))
    vectors = np.array([by_id[r["chunk_id"]] for r in rows])
    similarity = vectors @ np.array(embed([QUERY_PREFIX + query])[0])
    semantic = list(np.argsort(-similarity)[:CANDIDATES])

    fused: dict[int, float] = {}
    for ranking in (semantic, keyword):
        for rank, i in enumerate(ranking):
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (RRF_K + rank + 1)
    candidates = sorted(fused, key=fused.get, reverse=True)
    scores = reranker().predict([(query, rows[i]["text"]) for i in candidates])

    results = []
    for score, i in sorted(zip(scores, candidates), reverse=True)[:k]:
        row = rows[i] | {"score": float(score), "is_table": bool(rows[i]["is_table"]),
                         "is_amendment": bool(rows[i]["is_amendment"])}
        row["availability_time"] = datetime.fromisoformat(row["availability_time"]).astimezone(EASTERN)
        results.append(row)
    return results


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())
