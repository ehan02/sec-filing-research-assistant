"""Retrieval: metadata and As-of filter first, then BM25 over what's left.

Semantic search, reciprocal rank fusion and the cross-encoder are added in
ticket 04 behind the same ``search`` function.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from rank_bm25 import BM25Okapi

from src.filings.availability import EASTERN
from src.rag.index import connect

TOP_K = 5

_TOKEN = re.compile(r"\w+")


def search(db_path: Path, query: str, as_of: datetime, cik: int | None = None,
           form: str | None = None, fiscal_year: int | None = None,
           section: str | None = None, k: int = TOP_K) -> list[dict]:
    """Top ``k`` Chunks for ``query`` among those available at ``as_of``.

    Chunks that share no term with the query are never returned.
    """
    filters = {"cik": cik, "form": form, "fiscal_year": fiscal_year, "section": section}
    where = ["availability_time <= ?"] + [f"{col} = ?" for col, v in filters.items() if v is not None]
    params = [as_of.astimezone(timezone.utc).isoformat()] + [v for v in filters.values() if v is not None]
    with connect(db_path) as conn:
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM chunks WHERE {' AND '.join(where)}", params)]
    if not rows:
        return []

    corpus = [_tokens(r["text"]) for r in rows]
    query_tokens = _tokens(query)
    scores = BM25Okapi(corpus).get_scores(query_tokens)
    # BM25 scores can be <= 0 for a real match when every candidate contains the
    # term, so "shares a query term" decides what is a match, not the score.
    matches = [i for i, doc in enumerate(corpus) if not set(query_tokens).isdisjoint(doc)]
    results = []
    for i in sorted(matches, key=lambda i: scores[i], reverse=True)[:k]:
        row = rows[i] | {"score": float(scores[i]), "is_table": bool(rows[i]["is_table"]),
                         "is_amendment": bool(rows[i]["is_amendment"])}
        row["availability_time"] = datetime.fromisoformat(row["availability_time"]).astimezone(EASTERN)
        results.append(row)
    return results


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())
