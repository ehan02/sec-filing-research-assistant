"""Evaluation harness: numeric (vs XBRL), narrative, point-in-time and abstention sets.

Narrative set: Recall@5 of ``filing_search`` against hand-labeled evidence in
``tests/eval/narrative.json``. Each relevant item is a Filing, a Section and an
evidence phrase; it counts as retrieved when a top-5 Chunk from that Filing and
Section contains the phrase.

Run outside pytest, against a real index::

    python -m tests.eval_filings narrative
    python -m tests.eval_filings narrative --label minilm-rerank

Models come from ``EMBED_MODEL`` and ``RERANK_MODEL``. A different embedding
model needs its own index (``--db``) built with the same ``EMBED_MODEL``.
Each run writes ``data/eval/narrative-<label>.json`` so runs can be compared.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.agents.tools import filing_search
from src.filings.edgar import ROOT, EdgarClient, EdgarDownloader, _emit
from src.rag.index import CHUNKS_DB, EMBED_MODEL
from src.rag.retrieve import RERANK_MODEL

NARRATIVE_SET = Path(__file__).parent / "eval" / "narrative.json"
RESULTS_DIR = ROOT / "data" / "eval"


def run_narrative(db_path: Path, downloader: EdgarDownloader) -> dict:
    questions = json.loads(NARRATIVE_SET.read_text(encoding="utf-8"))["questions"]
    results = []
    for q in questions:
        hits = filing_search(q["question"], ticker=q["ticker"], as_of=q["as_of"],
                             downloader=downloader, db_path=db_path, **q["filters"])
        missed = [r for r in q["relevant"]
                  if not any(h["accession_no"] == r["accession_no"] and h["section"] == r["section"]
                             and r["phrase"].lower() in h["text"].lower() for h in hits)]
        results.append({
            "id": q["id"],
            "recall_at_5": 1 - len(missed) / len(q["relevant"]),
            "missed": missed,
            "retrieved": [f"{h['accession_no']} {h['section']}" for h in hits],
        })
    return {
        "set": "narrative",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "config": {"db": str(db_path), "embed_model": EMBED_MODEL, "rerank_model": RERANK_MODEL},
        "recall_at_5": sum(r["recall_at_5"] for r in results) / len(results),
        "questions": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an evaluation set against a real index.")
    parser.add_argument("set", choices=["narrative"])
    parser.add_argument("--db", type=Path, default=CHUNKS_DB, help="Chunks database to search")
    parser.add_argument("--label", default=datetime.now().strftime("%Y%m%d-%H%M%S"),
                        help="Name for this run's results file")
    args = parser.parse_args(argv)

    report = run_narrative(args.db, EdgarDownloader(EdgarClient()))
    for r in report["questions"]:
        _emit(f"  {r['recall_at_5']:>5.2f}  {r['id']}")
        for m in r["missed"]:
            _emit(f"         missed {m['accession_no']} {m['section']} {m['phrase']!r}")
    _emit(f"Recall@5 {report['recall_at_5']:.3f} over {len(report['questions'])} questions "
          f"(embed {EMBED_MODEL}, rerank {RERANK_MODEL})")

    out = RESULTS_DIR / f"narrative-{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _emit(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
