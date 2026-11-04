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

Numeric set: generated from the facts table, no hand labels. For each
headline concept and period, the value as first reported, asked As-of the
reporting Filing's Availability Time; scored by exact match within a relative
``--tolerance``.

Point-in-time set: seeded from every real Restatement in the facts table. Each
restated value is asked 1 second before and exactly at its Filing's
Availability Time; getting the restated value before then is a leak, reported
by name.

Both sets score through a ``lookup(question) -> value`` (``get_financials`` for
now), so end-to-end answers can be scored the same way::

    python -m tests.eval_filings numeric --tolerance 0.001
    python -m tests.eval_filings point-in-time

Each run writes ``data/eval/<set>-<label>.json`` so runs can be compared.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from src.agents.tools import FACTS_DB, filing_search, get_financials
from src.filings.availability import EASTERN
from src.filings.edgar import ROOT, EdgarClient, EdgarDownloader, _emit
from src.filings.xbrl import connect, fact_history
from src.rag.index import CHUNKS_DB, EMBED_MODEL
from src.rag.retrieve import RERANK_MODEL

NARRATIVE_SET = Path(__file__).parent / "eval" / "narrative.json"
RESULTS_DIR = ROOT / "data" / "eval"
NUMERIC_CONCEPTS = [
    "us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap:GrossProfit", "us-gaap:OperatingIncomeLoss", "us-gaap:NetIncomeLoss",
    "us-gaap:EarningsPerShareDiluted", "us-gaap:Assets", "us-gaap:StockholdersEquity",
]

Lookup = Callable[[dict], "float | None"]

# A Filing reporting two values for one concept and period (e.g. a duration and an
# instant that map to the same Fiscal Period) has no single right answer, so both sets skip it.
_UNAMBIGUOUS = """(cik, concept, fiscal_year, fiscal_period) NOT IN (
    SELECT cik, concept, fiscal_year, fiscal_period FROM facts
    GROUP BY cik, concept, fiscal_year, fiscal_period, accn HAVING COUNT(DISTINCT value) > 1)"""


def numeric_set(db_path: Path, downloader: EdgarDownloader, concepts: list[str]) -> list[dict]:
    """One question per Company, concept and period: the first reported value,
    As-of the Availability Time of the Filing that reported it."""
    tickers = _tickers(downloader)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM facts WHERE concept IN ({','.join('?' * len(concepts))}) AND {_UNAMBIGUOUS}"
            " ORDER BY cik, concept, fiscal_year, fiscal_period, availability_time", concepts).fetchall()
    first: dict[tuple, dict] = {}
    for r in rows:
        if r["cik"] in tickers:
            first.setdefault((r["cik"], r["concept"], r["fiscal_year"], r["fiscal_period"]), dict(r))
    questions = []
    for (cik, concept, fy, fp), r in first.items():
        period = _period(fy, fp)
        questions.append({"id": f"{tickers[cik]} {concept} {period}", "ticker": tickers[cik],
                          "concept": concept, "period": period, "as_of": _eastern(r["availability_time"]),
                          "expected": r["value"], "accession_no": r["accn"]})
    return questions


def point_in_time_set(db_path: Path, downloader: EdgarDownloader) -> list[dict]:
    """For every Restatement, the prior value asked 1 second before the
    restating Filing's Availability Time and the restated value asked at it."""
    tickers = _tickers(downloader)
    with connect(db_path) as conn:
        restated = conn.execute(
            f"SELECT cik, concept, fiscal_year, fiscal_period FROM facts WHERE {_UNAMBIGUOUS}"
            " GROUP BY cik, concept, fiscal_year, fiscal_period HAVING COUNT(DISTINCT value) > 1"
            " ORDER BY cik, concept, fiscal_year, fiscal_period").fetchall()
    questions = []
    for cik, concept, fy, fp in restated:
        if cik not in tickers:
            continue
        history = fact_history(db_path, cik, concept, fy, fp)
        for prior, new in zip(history, history[1:]):
            at = new["availability_time"]
            base = {"ticker": tickers[cik], "concept": concept, "period": _period(fy, fp),
                    "restated_value": new["value"], "restated_by": new["accn"]}
            name = f"{tickers[cik]} {concept} {_period(fy, fp)}"
            questions += [base | {"id": f"{name} before {new['accn']}", "phase": "before",
                                  "as_of": at - timedelta(seconds=1), "expected": prior["value"]},
                          base | {"id": f"{name} at {new['accn']}", "phase": "at",
                                  "as_of": at, "expected": new["value"]}]
    return questions


def financials_lookup(downloader: EdgarDownloader, db_path: Path) -> Lookup:
    """Answer a question with ``get_financials``."""
    return lambda q: get_financials(q["ticker"], [q["concept"]], [q["period"]], q["as_of"],
                                    downloader=downloader, db_path=db_path)[0]["value"]


def matches(expected: float, actual: float | None, tolerance: float) -> bool:
    """Exact match within a relative ``tolerance`` (0 means exactly equal)."""
    return actual is not None and abs(actual - expected) <= tolerance * abs(expected)


def run_numeric(questions: list[dict], lookup: Lookup, tolerance: float) -> dict:
    results = [q | {"actual": lookup(q)} for q in questions]
    failures = [_failure(r) for r in results if not matches(r["expected"], r["actual"], tolerance)]
    return {"set": "numeric", "tolerance": tolerance, "questions": len(results),
            "accuracy": 1 - len(failures) / len(results) if results else None, "failures": failures}


def run_point_in_time(questions: list[dict], lookup: Lookup, tolerance: float) -> dict:
    """Like ``run_numeric``; a "before" answer equal to the restated value is a leak."""
    report = run_numeric(questions, lookup, tolerance) | {"set": "point-in-time"}
    by_id = {q["id"]: q for q in questions}
    report["leaks"] = [f for f in report["failures"] if by_id[f["id"]]["phase"] == "before"
                       and matches(by_id[f["id"]]["restated_value"], f["actual"], tolerance)]
    return report


def _failure(result: dict) -> dict:
    return {"id": result["id"], "as_of": result["as_of"], "expected": result["expected"],
            "actual": result["actual"]}


def _period(fy: int, fp: str) -> str:
    return f"FY{fy}" if fp == "FY" else f"FY{fy} {fp}"


def _eastern(utc_iso: str) -> datetime:
    return datetime.fromisoformat(utc_iso).astimezone(EASTERN)


def _tickers(downloader: EdgarDownloader) -> dict[int, str]:
    """CIK to Ticker for every Company with saved Filings."""
    return {int(p.parent.parent.name): json.loads(p.read_text(encoding="utf-8"))["ticker"]
            for p in downloader.filings_dir.glob("*/*/metadata.json")}


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
    parser = argparse.ArgumentParser(description="Run an evaluation set against real data.")
    parser.add_argument("set", choices=["narrative", "numeric", "point-in-time"])
    parser.add_argument("--db", type=Path, default=CHUNKS_DB, help="Chunks database to search")
    parser.add_argument("--facts-db", type=Path, default=FACTS_DB, help="Facts database")
    parser.add_argument("--tolerance", type=float, default=0.0, help="Relative tolerance for numbers")
    parser.add_argument("--label", default=datetime.now().strftime("%Y%m%d-%H%M%S"),
                        help="Name for this run's results file")
    args = parser.parse_args(argv)
    downloader = EdgarDownloader(EdgarClient())

    if args.set == "narrative":
        report = run_narrative(args.db, downloader)
        for r in report["questions"]:
            _emit(f"  {r['recall_at_5']:>5.2f}  {r['id']}")
            for m in r["missed"]:
                _emit(f"         missed {m['accession_no']} {m['section']} {m['phrase']!r}")
        _emit(f"Recall@5 {report['recall_at_5']:.3f} over {len(report['questions'])} questions "
              f"(embed {EMBED_MODEL}, rerank {RERANK_MODEL})")
    else:
        lookup = financials_lookup(downloader, args.facts_db)
        if args.set == "numeric":
            report = run_numeric(numeric_set(args.facts_db, downloader, NUMERIC_CONCEPTS), lookup, args.tolerance)
        else:
            report = run_point_in_time(point_in_time_set(args.facts_db, downloader), lookup, args.tolerance)
        for f in report["failures"]:
            leak = "LEAK " if f in report.get("leaks", []) else ""
            _emit(f"  {leak}{f['id']} as of {f['as_of']:%Y-%m-%d %H:%M:%S}: "
                  f"expected {f['expected']}, got {f['actual']}")
        leaks = f", {len(report['leaks'])} leaks" if "leaks" in report else ""
        _emit(f"{args.set}: accuracy {report['accuracy']:.3f} over {report['questions']} questions"
              f"{leaks} (tolerance {args.tolerance})")

    out = RESULTS_DIR / f"{args.set}-{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _emit(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
