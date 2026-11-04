"""Chunk parsed Sections and store them, keyed by accession number.

Chunks are 300 words (about 360 tokens, at most ~500 in number-heavy text)
with 50 words of overlap, so the 512-token embedder and reranker see all of
each one; they never cross a Section boundary. Each table, with its caption, is
exactly one Chunk however long it is. Chunks live in a SQLite ``chunks`` table
that retrieval filters on before ranking, and their embeddings in the Chroma
``filings`` collection (in a ``chroma`` folder beside the database) under the
same chunk IDs.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timezone
from functools import cache
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from src.filings.edgar import ROOT, EdgarDownloader, _emit
from src.filings.parse import parse_10k
from src.filings.xbrl import fiscal_year

CHUNKS_DB = Path(os.getenv("CHUNKS_DB", ROOT / "data" / "chunks.db"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
CHUNK_WORDS = 300
OVERLAP_WORDS = 50

COLUMNS = ("chunk_id", "cik", "ticker", "company", "form", "is_amendment", "fiscal_year",
           "fiscal_period", "report_date", "availability_time", "accession_no", "section",
           "chunk_idx", "is_table", "url", "text")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS chunks ({", ".join(COLUMNS)}, PRIMARY KEY (chunk_id));
CREATE INDEX IF NOT EXISTS chunks_accession ON chunks (accession_no);
CREATE INDEX IF NOT EXISTS chunks_filter ON chunks (cik, form, availability_time);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def collection(db_path: Path) -> chromadb.Collection:
    """The Chroma ``filings`` collection that belongs to this chunks database."""
    client = chromadb.PersistentClient(path=str(db_path.with_name("chroma")),
                                       settings=chromadb.Settings(anonymized_telemetry=False))
    return client.get_or_create_collection("filings", metadata={"hnsw:space": "cosine"})


@cache
def embedder(model: str = EMBED_MODEL) -> SentenceTransformer:
    return SentenceTransformer(model)


def embed(texts: list[str]) -> list[list[float]]:
    return embedder().encode(texts, normalize_embeddings=True, batch_size=16).tolist()


def chunk_section(blocks: list[dict]) -> list[dict]:
    """Chunks of one Section: tables whole, text in overlapping word windows."""
    chunks: list[dict] = []
    words: list[str] = []

    def flush() -> None:
        start = 0
        while start < len(words):
            chunks.append({"text": " ".join(words[start:start + CHUNK_WORDS]), "is_table": False})
            if start + CHUNK_WORDS >= len(words):
                break
            start += CHUNK_WORDS - OVERLAP_WORDS
        words.clear()

    for block in blocks:
        if block["is_table"]:
            flush()
            chunks.append(block)
        else:
            words += block["text"].split()
    flush()
    return chunks


def index_company(downloader: EdgarDownloader, ticker: str, db_path: Path = CHUNKS_DB) -> dict[str, int]:
    """(Re)index every saved Original 10-K of a Company. Returns Chunk counts per accession."""
    cik, _ = downloader.lookup(ticker)
    sub_path = downloader.cache_dir / "submissions" / f"CIK{cik:010d}.json"
    fye = json.loads(sub_path.read_text(encoding="utf-8"))["fiscalYearEnd"]

    counts: dict[str, int] = {}
    for meta_path in sorted((downloader.filings_dir / str(cik)).glob("*/metadata.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta["form"] != "10-K":
            continue
        sections = parse_10k((meta_path.parent / meta["primary_document"]).read_bytes())
        if not sections:
            _emit(f"  ! {meta['accession_no']}: no Sections found, not indexed")
        rows = []
        for section in sections:
            for idx, chunk in enumerate(chunk_section(section["blocks"])):
                rows.append({
                    "chunk_id": f"{meta['accession_no']}:{section['section']}:{idx}",
                    "cik": cik,
                    "ticker": meta["ticker"],
                    "company": meta["company"],
                    "form": meta["form"],
                    "is_amendment": meta["is_amendment"],
                    "fiscal_year": fiscal_year(date.fromisoformat(meta["report_date"]), fye),
                    "fiscal_period": "FY",
                    "report_date": meta["report_date"],
                    "availability_time": datetime.fromisoformat(meta["availability_time"])
                                                 .astimezone(timezone.utc).isoformat(),
                    "accession_no": meta["accession_no"],
                    "section": section["section"],
                    "chunk_idx": idx,
                    "is_table": chunk["is_table"],
                    "url": meta["url"],
                    "text": chunk["text"],
                })
        with connect(db_path) as conn:
            conn.execute("DELETE FROM chunks WHERE accession_no = ?", (meta["accession_no"],))
            conn.executemany(f"INSERT INTO chunks VALUES ({', '.join('?' * len(COLUMNS))})",
                             [tuple(r[c] for c in COLUMNS) for r in rows])
        vectors = collection(db_path)
        vectors.delete(where={"accession_no": meta["accession_no"]})
        if rows:
            vectors.add(ids=[r["chunk_id"] for r in rows],
                        embeddings=embed([r["text"] for r in rows]),
                        metadatas=[{"accession_no": r["accession_no"]} for r in rows])
        counts[meta["accession_no"]] = len(rows)
    return counts
