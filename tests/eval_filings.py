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

End to end (``all``), every set runs through the router under one named
configuration (LLM, embedding model via ``EMBED_MODEL`` and ``--db``):
narrative answers are scored for citation validity (every Citation names a
real Chunk or Fact) and faithfulness (a judge model checks each cited sentence
against the cited text); numeric and point-in-time questions are asked at
their exact As-of; ``tests/eval/abstention.json`` is scored by correct-decline
rate. ``compare`` puts runs side by side in ``data/eval/comparison.md``::

    python -m tests.eval_filings all --llm ollama --limit 5 --label ollama-bge
    python -m tests.eval_filings compare ollama-bge claude-bge

Each run writes ``data/eval/<set>-<label>.json`` so runs can be compared.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from src.agents.agent import ask
from src.agents.tools import FACTS_DB, filing_search, get_financials
from src.filings.availability import EASTERN
from src.filings.edgar import ROOT, EdgarClient, EdgarDownloader, _emit
from src.filings.xbrl import connect, fact_history
from src.rag.answer import _CITATION, ChatFn, chat_model, citation
from src.rag.index import CHUNKS_DB, EMBED_MODEL
from src.rag.index import connect as index_connect
from src.rag.retrieve import RERANK_MODEL

NARRATIVE_SET = Path(__file__).parent / "eval" / "narrative.json"
ABSTENTION_SET = Path(__file__).parent / "eval" / "abstention.json"
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


# -- end-to-end answer quality ---------------------------------------------------

JUDGE = """You check whether a claim is supported by source text from SEC filings. \
Reply with exactly "yes" if the source text supports every statement in the claim, otherwise "no"."""

Answer = Callable[[dict], dict]
# Like the post-check's number pattern, but keeping a minus sign: a loss must read back negative.
_SIGNED_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def router_lookup(chat: ChatFn, downloader: EdgarDownloader, chunks_db: Path, facts_db: Path) -> Lookup:
    """Ask a numeric question through the router at its exact As-of, and read back the
    stated number closest to the expected value (None if it abstained or failed)."""
    def lookup(q: dict) -> float | None:
        question = f"What was {q['ticker']}'s {q['concept']} for {q['period']}?"
        try:
            r = ask(question, chat, q["as_of"], downloader=downloader, chunks_db=chunks_db, facts_db=facts_db)
        except Exception:
            return None
        numbers = [float(n.replace(",", "")) for n in _SIGNED_NUMBER.findall(_CITATION.sub("", r["answer"]))]
        return None if r["abstained"] else min(numbers, key=lambda n: abs(n - q["expected"]), default=None)
    return lookup


def valid_citations(chunks_db: Path, facts_db: Path, downloader: EdgarDownloader) -> set[str]:
    """Every Citation that names a real Chunk's Filing and Section, or a real Fact."""
    with index_connect(chunks_db) as conn:
        chunks = conn.execute("SELECT DISTINCT ticker, form, fiscal_year, fiscal_period, section, accession_no"
                              " FROM chunks").fetchall()
    tickers = _tickers(downloader)
    with connect(facts_db) as conn:
        facts = conn.execute("SELECT DISTINCT cik, concept, fiscal_year, fiscal_period, accn FROM facts").fetchall()
    return ({citation(dict(c)) for c in chunks}
            | {f"{tickers[f['cik']]} {f['concept']} {_period(f['fiscal_year'], f['fiscal_period'])}, {f['accn']}"
               for f in facts if f["cik"] in tickers})


def faithfulness(answer: str, sources: dict[str, str], judge: ChatFn) -> tuple[int, list[str]]:
    """Ask ``judge`` whether each cited sentence is supported by the text of its Citations.
    Returns the number supported and the unsupported sentences."""
    supported, unsupported = 0, []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer.strip()):  # a bullet line is its own claim
        sentence = sentence.strip()
        cited = _CITATION.findall(sentence)
        if not cited:
            continue
        text = "\n\n".join(sources.get(c, "") for c in cited)
        claim = _CITATION.sub("", sentence).strip()
        reply = judge(JUDGE, [{"role": "user", "content": f"Source text:\n{text}\n\nClaim: {claim}"}])
        if reply.strip().lower().startswith("yes"):
            supported += 1
        else:
            unsupported.append(sentence)
    return supported, unsupported


def run_answers(questions: list[dict], answer: Answer, judge: ChatFn, valid: set[str]) -> dict:
    """Citation validity (share of answers whose Citations are all real) and
    faithfulness (share of cited sentences the judge finds supported)."""
    report = {"set": "narrative-answers", "questions": len(questions), "invalid": [], "unsupported": [],
              "abstained": [], "errors": []}
    answered = supported = judged = 0
    for q in questions:
        r = _attempt(answer, q, report)
        if r is None:
            continue
        if r["abstained"]:
            report["abstained"].append(q["id"])
            continue
        answered += 1
        cited = _CITATION.findall(r["answer"])
        bad = [c for c in cited if c not in valid]
        if bad or not cited:
            report["invalid"].append({"id": q["id"], "citations": bad})
        n, unsupported = faithfulness(r["answer"], r.get("sources", {}), judge)
        supported, judged = supported + n, judged + n + len(unsupported)
        report["unsupported"] += [{"id": q["id"], "sentence": s} for s in unsupported]
    report["citation_validity"] = 1 - len(report["invalid"]) / answered if answered else None
    report["faithfulness"] = supported / judged if judged else None
    return report


def run_abstention(questions: list[dict], answer: Answer) -> dict:
    """Correct-decline rate: the share of questions answered with the Abstention sentence."""
    report = {"set": "abstention", "questions": len(questions), "failures": [], "errors": []}
    declined = 0
    for q in questions:
        r = _attempt(answer, q, report)
        if r is not None and r["abstained"]:
            declined += 1
        elif r is not None:
            report["failures"].append(q["id"])
    report["correct_decline_rate"] = declined / len(questions) if questions else None
    return report


def compare(reports: dict[str, dict]) -> str:
    """A markdown table of each configuration's metrics, side by side."""
    metrics = list(dict.fromkeys(m for r in reports.values() for m in r["metrics"]))
    lines = ["| Metric | " + " | ".join(reports) + " |", "|---" * (len(reports) + 1) + "|"]
    for m in metrics:
        cells = [r["metrics"].get(m) for r in reports.values()]
        lines.append(f"| {m} | " + " | ".join(
            "–" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v) for v in cells) + " |")
    return "\n".join(lines)


def run_all(chat: ChatFn, judge: ChatFn, downloader: EdgarDownloader, chunks_db: Path, facts_db: Path,
            limit: int | None, tolerance: float) -> dict:
    """Every set end-to-end through the router, plus narrative Recall@5."""
    def answer(q: dict) -> dict:
        return ask(q["question"], chat, q["as_of"], downloader=downloader, chunks_db=chunks_db, facts_db=facts_db)

    narrative = json.loads(NARRATIVE_SET.read_text(encoding="utf-8"))["questions"]
    abstention = json.loads(ABSTENTION_SET.read_text(encoding="utf-8"))["questions"]
    pit = point_in_time_set(facts_db, downloader)
    pairs = _sample(list(zip(pit[0::2], pit[1::2])), limit)
    lookup = router_lookup(chat, downloader, chunks_db, facts_db)
    sets = {
        "narrative": run_narrative(chunks_db, downloader),
        "narrative-answers": run_answers(_sample(narrative, limit), answer, judge,
                                         valid_citations(chunks_db, facts_db, downloader)),
        "numeric": run_numeric(_sample(numeric_set(facts_db, downloader, NUMERIC_CONCEPTS), limit), lookup, tolerance),
        "point-in-time": run_point_in_time([q for pair in pairs for q in pair], lookup, tolerance),
        "abstention": run_abstention(_sample(abstention, limit), answer),
    }
    metrics = {
        "narrative_recall_at_5": sets["narrative"]["recall_at_5"],
        "narrative_citation_validity": sets["narrative-answers"]["citation_validity"],
        "narrative_faithfulness": sets["narrative-answers"]["faithfulness"],
        "numeric_accuracy": sets["numeric"]["accuracy"],
        "point_in_time_accuracy": sets["point-in-time"]["accuracy"],
        "point_in_time_leaks": len(sets["point-in-time"]["leaks"]),
        "abstention_correct_decline_rate": sets["abstention"]["correct_decline_rate"],
    }
    return {"metrics": metrics, "sets": sets}


def _attempt(answer: Answer, q: dict, report: dict) -> dict | None:
    try:
        return answer(q)
    except Exception as exc:
        report["errors"].append({"id": q["id"], "error": f"{type(exc).__name__}: {exc}"})
        return None


def _sample(items: list, n: int | None) -> list:
    """``n`` items spread evenly over ``items`` (all of them if ``n`` is None)."""
    if n is None or len(items) <= n:
        return items
    return [items[i * len(items) // n] for i in range(n)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an evaluation set against real data.")
    parser.add_argument("set", choices=["narrative", "numeric", "point-in-time", "all", "compare"])
    parser.add_argument("labels", nargs="*", help="compare: the 'all' run labels to put side by side")
    parser.add_argument("--db", type=Path, default=CHUNKS_DB, help="Chunks database to search")
    parser.add_argument("--facts-db", type=Path, default=FACTS_DB, help="Facts database")
    parser.add_argument("--tolerance", type=float, default=0.0, help="Relative tolerance for numbers")
    parser.add_argument("--llm", choices=["ollama", "anthropic"], help="all: answering model (default DEFAULT_LLM)")
    parser.add_argument("--judge-llm", choices=["ollama", "anthropic"], help="all: faithfulness judge (default --llm)")
    parser.add_argument("--limit", type=int, help="all: at most this many questions per set")
    parser.add_argument("--label", default=datetime.now().strftime("%Y%m%d-%H%M%S"),
                        help="Name for this run's results file")
    args = parser.parse_args(argv)

    if args.set == "compare":
        reports = {label: json.loads((RESULTS_DIR / f"all-{label}.json").read_text(encoding="utf-8"))
                   for label in args.labels}
        table = compare(reports)
        out = RESULTS_DIR / "comparison.md"
        out.write_text(table + "\n", encoding="utf-8")
        _emit(table)
        _emit(f"Wrote {out}")
        return 0

    downloader = EdgarDownloader(EdgarClient())
    if args.set == "narrative":
        report = run_narrative(args.db, downloader)
        for r in report["questions"]:
            _emit(f"  {r['recall_at_5']:>5.2f}  {r['id']}")
            for m in r["missed"]:
                _emit(f"         missed {m['accession_no']} {m['section']} {m['phrase']!r}")
        _emit(f"Recall@5 {report['recall_at_5']:.3f} over {len(report['questions'])} questions "
              f"(embed {EMBED_MODEL}, rerank {RERANK_MODEL})")
    elif args.set == "all":
        llm = args.llm or os.getenv("DEFAULT_LLM", "ollama")
        judge_llm = args.judge_llm or llm
        chat = chat_model(llm)
        report = run_all(chat, chat if judge_llm == llm else chat_model(judge_llm), downloader,
                         args.db, args.facts_db, args.limit, args.tolerance)
        report["config"] = {
            "label": args.label, "llm": llm,
            "llm_model": os.getenv("OLLAMA_MODEL" if llm == "ollama" else "ANTHROPIC_MODEL"),
            "judge_llm": judge_llm, "embed_model": EMBED_MODEL, "rerank_model": RERANK_MODEL,
            "db": str(args.db), "limit": args.limit, "tolerance": args.tolerance,
            "run_at": datetime.now().isoformat(timespec="seconds")}
        for name, value in report["metrics"].items():
            _emit(f"  {name:<34} {'–' if value is None else round(value, 3)}")
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
