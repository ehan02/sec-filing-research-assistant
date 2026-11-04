"""Build and run the LangGraph router: plan → one route node → answer."""

from __future__ import annotations

from datetime import date, datetime
from functools import partial
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from src.agents import nodes
from src.agents.tools import FACTS_DB
from src.filings.edgar import EdgarClient, EdgarDownloader
from src.rag.answer import ChatFn
from src.rag.index import CHUNKS_DB


def ask(question: str, chat: ChatFn, as_of: datetime | date | str | None = None, *,
        downloader: EdgarDownloader | None = None, chunks_db: Path = CHUNKS_DB,
        facts_db: Path = FACTS_DB) -> dict:
    """Answer ``question`` through the router.

    ``as_of`` overrides any date in the question; with neither, it is now.
    Returns the answer, its Citations, whether it abstained, the route taken,
    the As-of used, and ``per_company`` results.
    """
    deps = {"chat": chat, "downloader": downloader or EdgarDownloader(EdgarClient()),
            "chunks_db": chunks_db, "facts_db": facts_db}
    graph = StateGraph(nodes.State)
    graph.add_node("plan", partial(nodes.plan, chat=chat))
    for route in nodes.ROUTES:
        # Looked up at call time, so tests can spy on the tools the nodes use.
        graph.add_node(route, lambda state, _r=route: getattr(nodes, _r)(state, **deps))
        graph.add_edge(route, END)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", lambda state: state["plan"]["route"], list(nodes.ROUTES))

    state = graph.compile().invoke({"question": question, "as_of": as_of})
    return state["result"] | {"route": state["plan"]["route"], "as_of": state["as_of"]}
