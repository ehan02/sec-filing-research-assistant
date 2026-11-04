"""The router agent with a scripted chat model: one question of each type, over the fixture Universe."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.agents import nodes
from src.agents.agent import ask
from src.filings.availability import EASTERN, normalize_as_of
from src.filings.xbrl import load_facts
from src.rag.answer import ABSTAIN
from tests import fixture_universe as fu
from tests.fakes import ScriptedChat

REVENUE = "us-gaap:Revenues"
RISK = f"FIXT 10-K FY2023 Item 1A, {fu.ACC_10K_2023}"
REV_2023 = f"FIXT {REVENUE} FY2023, {fu.ACC_10K_2023}"
RISK_PLAN = {"tickers": ["FIXT"], "query": "export restrictions risk", "form": "10-K", "latest": True}


@pytest.fixture
def env(universe, chunks_db, tmp_path, monkeypatch):
    facts_db = tmp_path / "facts.db"
    load_facts(universe.downloader, fu.TICKER, facts_db)
    calls = []
    for name in ("filing_search", "get_financials", "section_diff"):
        def spy(*args, _real=getattr(nodes, name), _name=name, **kw):
            calls.append((_name, kw))
            return _real(*args, **kw)
        monkeypatch.setattr(nodes, name, spy)
    return SimpleNamespace(universe=universe, chunks_db=chunks_db, facts_db=facts_db, calls=calls)


def _ask(env, plan, *answers, as_of=None, question="The analyst's question"):
    chat = ScriptedChat(plan if isinstance(plan, str) else json.dumps(plan), *answers)
    result = ask(question, chat, as_of, downloader=env.universe.downloader,
                 chunks_db=env.chunks_db, facts_db=env.facts_db)
    return result, chat


def _tools(env):
    return [name for name, _ in env.calls]


def test_narrative_question_searches_with_an_explicit_as_of_of_now(env):
    answer = f"New export restrictions could block sales [{RISK}]."
    result, _ = _ask(env, RISK_PLAN | {"route": "narrative"}, answer)

    assert (result["route"], result["answer"], result["citations"]) == ("narrative", answer, [RISK])
    [(tool, kw)] = env.calls
    assert (tool, kw["ticker"], kw["form"], kw["latest"]) == ("filing_search", "FIXT", "10-K", True)
    assert kw["as_of"].tzinfo is not None
    assert abs(kw["as_of"] - datetime.now(EASTERN)) < timedelta(minutes=1)


def test_numeric_question_uses_the_as_of_from_the_question(env):
    plan = {"route": "numeric", "tickers": ["FIXT"], "as_of": "2024-06-01",
            "concepts": [REVENUE], "periods": ["FY2022", "FY2023"]}
    answer = f"FY2023 revenue was 1,200,000,000 USD, up 20.0% [{REV_2023}]."
    result, chat = _ask(env, plan, answer, question="What was FIXT's revenue as of 2024-06-01?")

    assert (result["route"], result["citations"]) == ("numeric", [REV_2023])
    [(tool, kw)] = env.calls
    assert (tool, kw["concepts"], kw["periods"]) == ("get_financials", [REVENUE], ["FY2022", "FY2023"])
    assert kw["as_of"] == normalize_as_of("2024-06-01")
    assert "+200,000,000 USD (+20.0%)" in chat.calls[1][1][0]["content"]


def test_as_of_date_not_in_the_question_is_ignored(env):
    answer = f"New export restrictions could block sales [{RISK}]."
    _ask(env, RISK_PLAN | {"route": "narrative", "as_of": "2024-03-15"}, answer)
    [(_, kw)] = env.calls
    assert abs(kw["as_of"] - datetime.now(EASTERN)) < timedelta(minutes=1)


def test_change_question_diffs_the_section_and_cites_both_filings(env):
    plan = {"route": "change", "tickers": ["FIXT"], "section": "Item 1A", "form": "10-K",
            "fiscal_year_a": 2022, "fiscal_year_b": 2023}
    answer = f"A new export-restrictions risk was added [{RISK}]."
    result, chat = _ask(env, plan, answer, as_of="2024-06-01")

    assert (result["route"], result["citations"]) == ("change", [RISK])
    [(tool, kw)] = env.calls
    assert (tool, kw["fiscal_year_a"], kw["fiscal_year_b"]) == ("section_diff", 2022, 2023)
    assert kw["as_of"] == normalize_as_of("2024-06-01")
    assert "Added in FY2023: New export restrictions" in chat.calls[1][1][0]["content"]


def test_combined_question_gives_one_answer_with_both_kinds_of_citation(env):
    plan = RISK_PLAN | {"route": "combined", "concepts": [REVENUE], "periods": ["FY2023"]}
    answer = (f"Revenue was 1,200,000,000 USD in FY2023 [{REV_2023}], "
              f"while export restrictions could block sales [{RISK}].")
    result, chat = _ask(env, plan, answer)

    assert (result["route"], result["citations"]) == ("combined", sorted([REV_2023, RISK]))
    assert _tools(env) == ["get_financials", "filing_search"]
    given = chat.calls[1][1][0]["content"]
    assert "<facts>" in given and "<documents>" in given


def test_universe_wide_question_runs_per_company(env):
    answer = f"Export restrictions are a risk [{RISK}]."
    result, _ = _ask(env, RISK_PLAN | {"route": "narrative", "tickers": ["*"]}, answer)

    assert [kw["ticker"] for _, kw in env.calls] == ["FIXT"]
    assert result["per_company"]["FIXT"]["citations"] == [RISK]


@pytest.mark.parametrize("plan", [{"route": "abstain"}, "not a plan"])
def test_future_or_unplannable_question_abstains_without_tools(env, plan):
    result, chat = _ask(env, plan)
    assert (result["answer"], result["abstained"]) == (ABSTAIN, True)
    assert env.calls == [] and len(chat.calls) == 1
