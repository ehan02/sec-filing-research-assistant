"""LangGraph nodes: plan the question, call tools per Company, generate the answer.

The plan node asks the chat model for a JSON plan; each route node runs its
tools for every planned Company with the explicit As-of the plan node fixed,
and hands the tool output to a generator in ``src.rag.answer``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypedDict

from src.agents.tools import filing_search, get_financials, section_diff
from src.filings.availability import normalize_as_of
from src.filings.edgar import EdgarDownloader
from src.rag.answer import ABSTAIN, ChatFn, answer_combined, answer_from_chunks, answer_from_diff, answer_from_facts

ROUTES = ("narrative", "numeric", "change", "combined", "abstain")
PLAN_KEYS = {"route", "tickers", "as_of", "query", "form", "section", "fiscal_year", "latest", "concepts",
             "periods", "ratios", "fiscal_year_a", "fiscal_year_b"}

PLANNER = """You plan how to answer a question about companies' SEC filings. Reply with one JSON \
object and nothing else, with these keys:

- "route": "narrative" (what a filing says), "numeric" (reported financial values, margins, growth), \
"change" (what changed in a Section between two fiscal years), "combined" (numbers and narrative \
together), or "abstain" (the future, forecasts or guidance, or anything SEC filings don't contain).
- "tickers": the companies' tickers, or ["*"] for every company in the universe.
- "as_of": the date the question is asked as of, copied as written in "YYYY-MM-DD" form, or null \
if the question gives no such date. Never make one up.
- narrative and combined: "query" (search text), and optional "form" ("10-K", "10-Q", "8-K", or an \
amendment like "10-K/A"), "section" (e.g. "Item 1A", "Item 7", "Part I Item 2", "Ex-99.1"), \
"fiscal_year", and "latest": true for "the latest" filing of that form.
- numeric and combined: "concepts" (XBRL concepts like "us-gaap:Revenues", \
"us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:GrossProfit", \
"us-gaap:NetIncomeLoss"), "periods" (in order, like "FY2023" or "FY2024 Q1"), and optional "ratios" \
mapping a name to [numerator concept, denominator concept], e.g. {"gross margin": \
["us-gaap:GrossProfit", "us-gaap:Revenues"]}. Never compute values yourself.
- change: "section", "form", "fiscal_year_a" (earlier) and "fiscal_year_b" (later)."""


class State(TypedDict, total=False):
    question: str
    as_of: datetime | None
    plan: dict[str, Any]
    result: dict[str, Any]


def plan(state: State, chat: ChatFn) -> State:
    """Ask for a plan and fix the As-of: the caller's, else the question's, else now.

    The plan's date counts only if it appears verbatim in the question: small
    models invent one when the question has none, which would hide recent Filings.
    """
    reply = chat(PLANNER, [{"role": "user", "content": f"Question: {state['question']}"}])
    try:
        p = json.loads(reply[reply.index("{"):reply.rindex("}") + 1])
    except ValueError:
        p = {}
    if not isinstance(p, dict) or p.get("route") not in ROUTES:
        p = {"route": "abstain"}
    p = _normalize(p, state["question"])
    asked = p.get("as_of") if str(p.get("as_of")) in state["question"] else None
    return {"plan": p, "as_of": normalize_as_of(state.get("as_of") or asked)}


def _normalize(p: dict[str, Any], question: str) -> dict[str, Any]:
    """Repair what small models get wrong: arguments nested under another key,
    a bare Ticker string, fiscal years as text, and search filters the question
    never asked for (an invented Section or Fiscal Year finds nothing)."""
    for key, value in list(p.items()):
        if isinstance(value, dict) and value and set(value) <= PLAN_KEYS:
            del p[key]
            for k, v in value.items():
                p.setdefault(k, v)
    if isinstance(p.get("tickers"), str):
        p["tickers"] = [p["tickers"]]
    for key in ("fiscal_year", "fiscal_year_a", "fiscal_year_b"):
        year = re.fullmatch(r"(?:FY)?\s*(\d{4})", str(p.get(key) or "").strip(), re.IGNORECASE)
        p[key] = int(year.group(1)) if year else None
    if p["route"] in ("narrative", "combined"):
        if p.get("section") and str(p["section"]).lower() not in question.lower():
            p["section"] = None
        if p["fiscal_year"] and str(p["fiscal_year"]) not in question:
            p["fiscal_year"] = None
    return p


def narrative(state: State, chat: ChatFn, downloader: EdgarDownloader, chunks_db: Path, **_) -> State:
    return _per_company(state, downloader,
                        lambda t: answer_from_chunks(state["question"], chat, _search(state, t, downloader, chunks_db)))


def numeric(state: State, chat: ChatFn, downloader: EdgarDownloader, facts_db: Path, **_) -> State:
    p = state["plan"]
    return _per_company(state, downloader, lambda t: answer_from_facts(
        state["question"], chat, t, _financials(state, t, downloader, facts_db), p.get("ratios")))


def change(state: State, chat: ChatFn, downloader: EdgarDownloader, **_) -> State:
    p = state["plan"]

    def run(ticker: str) -> dict:
        try:
            diff = section_diff(ticker=ticker, section=p.get("section", "Item 1A"), form=p.get("form", "10-K"),
                                fiscal_year_a=p["fiscal_year_a"], fiscal_year_b=p["fiscal_year_b"],
                                as_of=state["as_of"], downloader=downloader)
        except (KeyError, ValueError):
            return _abstention()
        return answer_from_diff(state["question"], chat, diff)
    return _per_company(state, downloader, run)


def combined(state: State, chat: ChatFn, downloader: EdgarDownloader, chunks_db: Path, facts_db: Path,
             **_) -> State:
    p = state["plan"]
    return _per_company(state, downloader, lambda t: answer_combined(
        state["question"], chat, t, _financials(state, t, downloader, facts_db),
        _search(state, t, downloader, chunks_db), p.get("ratios")))


def abstain(state: State, **_) -> State:
    return {"result": _abstention()}


def _search(state: State, ticker: str, downloader: EdgarDownloader, db_path: Path) -> list[dict]:
    p = state["plan"]
    return filing_search(query=p.get("query") or state["question"], ticker=ticker, form=p.get("form"),
                         fiscal_year=p.get("fiscal_year"), section=p.get("section"), as_of=state["as_of"],
                         latest=bool(p.get("latest")), downloader=downloader, db_path=db_path)


def _financials(state: State, ticker: str, downloader: EdgarDownloader, db_path: Path) -> list[dict]:
    p = state["plan"]
    return get_financials(ticker=ticker, concepts=p.get("concepts", []), periods=p.get("periods", []),
                          as_of=state["as_of"], downloader=downloader, db_path=db_path)


def _per_company(state: State, downloader: EdgarDownloader, run: Callable[[str], dict]) -> State:
    """Run ``run`` for each planned Ticker (``*`` = the whole Universe) and merge the results."""
    tickers = state["plan"].get("tickers") or []
    if "*" in tickers:
        tickers = universe_tickers(downloader)
    results = {t.upper(): run(t.upper()) for t in tickers}
    if not results:
        return {"result": _abstention()}
    if len(results) == 1:
        [only] = results.values()
        return {"result": only | {"per_company": results}}
    return {"result": {
        "answer": "\n\n".join(f"{t}: {r['answer']}" for t, r in results.items()),
        "citations": sorted({c for r in results.values() for c in r["citations"]}),
        "abstained": all(r["abstained"] for r in results.values()),
        "sources": {c: t for r in results.values() for c, t in r.get("sources", {}).items()},
        "per_company": results,
    }}


def universe_tickers(downloader: EdgarDownloader) -> list[str]:
    """Tickers of every Company with saved Filings."""
    return sorted({json.loads(p.read_text(encoding="utf-8"))["ticker"]
                   for p in downloader.filings_dir.glob("*/*/metadata.json")})


def _abstention() -> dict:
    return {"answer": ABSTAIN, "citations": [], "attempts": 0, "abstained": True}
