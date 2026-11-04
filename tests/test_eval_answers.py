"""End-to-end answer-quality scoring with scripted models, over the fixture Universe."""

from __future__ import annotations

import json

import pytest

from src.filings.xbrl import load_facts
from src.rag.answer import ABSTAIN
from tests import fixture_universe as fu
from tests.eval_filings import (
    compare,
    faithfulness,
    point_in_time_set,
    router_lookup,
    run_abstention,
    run_answers,
    valid_citations,
)
from tests.fakes import ScriptedChat

RISK = f"FIXT 10-K FY2023 Item 1A, {fu.ACC_10K_2023}"
BOGUS = f"FIXT 10-K FY2023 Item 9Z, {fu.ACC_10K_2023}"
NET_INCOME = "us-gaap:NetIncomeLoss"


@pytest.fixture
def facts_db(universe, tmp_path):
    path = tmp_path / "facts.db"
    load_facts(universe.downloader, fu.TICKER, path)
    return path


def _answered(text, sources=None):
    return {"answer": text, "abstained": False, "citations": [], "sources": sources or {}}


def test_abstention_set_scores_the_correct_decline_rate():
    replies = iter([{"answer": ABSTAIN, "abstained": True}, _answered("FY2028 revenue will grow.")])

    def answer(q):
        if q["id"] == "crash":
            raise RuntimeError("model unavailable")
        return next(replies)

    questions = [{"id": i, "question": "q", "as_of": None} for i in ("declined", "answered", "crash")]
    report = run_abstention(questions, answer)
    assert report["correct_decline_rate"] == pytest.approx(1 / 3)
    assert report["failures"] == ["answered"]
    assert report["errors"] == [{"id": "crash", "error": "RuntimeError: model unavailable"}]


def test_citation_validity_checks_every_citation_against_real_chunks(universe, chunks_db, facts_db):
    valid = valid_citations(chunks_db, facts_db, universe.downloader)
    assert RISK in valid and f"FIXT {NET_INCOME} FY2022, {fu.ACC_10K_2023}" in valid and BOGUS not in valid

    replies = {"good": _answered(f"Export rules are a risk [{RISK}].", {RISK: "export restrictions"}),
               "bad": _answered(f"Export rules are a risk [{BOGUS}].", {BOGUS: "export restrictions"}),
               "declined": {"answer": ABSTAIN, "abstained": True}}
    questions = [{"id": i, "question": "q", "as_of": None} for i in replies]
    report = run_answers(questions, lambda q: replies[q["id"]], ScriptedChat("yes", "yes"), valid)

    assert report["citation_validity"] == 0.5  # over the two answered questions
    assert report["invalid"] == [{"id": "bad", "citations": [BOGUS]}]
    assert report["abstained"] == ["declined"]


def test_faithfulness_asks_the_judge_about_each_cited_sentence():
    answer = f"Export rules are a risk [{RISK}]. Sales are concentrated in Asia [{RISK}]. In summary, risks."
    judge = ScriptedChat("Yes, supported.", "no")
    supported, unsupported = faithfulness(answer, {RISK: "New export restrictions could block sales."}, judge)

    assert (supported, unsupported) == (1, [f"Sales are concentrated in Asia [{RISK}]."])
    assert len(judge.calls) == 2  # the uncited summary isn't judged
    prompt = judge.calls[0][1][0]["content"]
    assert "New export restrictions could block sales." in prompt and "Export rules are a risk" in prompt


def test_each_bullet_line_is_judged_on_its_own():
    answer = f"Apple names these risks:\n\n* Export rules [{RISK}]\n* Customer concentration [{RISK}]"
    judge = ScriptedChat("yes", "no")
    assert faithfulness(answer, {RISK: "export restrictions"}, judge) == (1, [f"* Customer concentration [{RISK}]"])


def test_numeric_lookup_keeps_the_sign_of_a_stated_number(universe, chunks_db, facts_db):
    q = {"ticker": "FIXT", "concept": NET_INCOME, "period": "FY2022", "as_of": None, "expected": -100_000_000}
    plan = {"route": "numeric", "tickers": ["FIXT"], "concepts": [NET_INCOME], "periods": ["FY2023"]}
    chat = ScriptedChat(json.dumps(plan),
                        f"Net income was -150,000,000 USD [FIXT {NET_INCOME} FY2023, {fu.ACC_10K_2023}].")
    assert router_lookup(chat, universe.downloader, chunks_db, facts_db)(q) == -150_000_000


def test_numeric_question_runs_through_the_router_at_its_exact_as_of(universe, chunks_db, facts_db):
    before = point_in_time_set(facts_db, universe.downloader)[0]  # 1 s before the restatement
    plan = {"route": "numeric", "tickers": ["FIXT"], "concepts": [NET_INCOME], "periods": ["FY2022"]}
    chat = ScriptedChat(json.dumps(plan),
                        f"Net income was 100,000,000 USD [FIXT {NET_INCOME} FY2022, {fu.ACC_10K_2022}].")
    lookup = router_lookup(chat, universe.downloader, chunks_db, facts_db)

    assert lookup(before) == 100_000_000
    question = chat.calls[0][1][0]["content"]
    assert NET_INCOME in question and "FY2022" in question


def test_compare_lays_configurations_side_by_side():
    table = compare({"ollama": {"metrics": {"numeric_accuracy": 0.9, "point_in_time_leaks": 0}},
                     "claude": {"metrics": {"numeric_accuracy": 1.0}}})
    assert "| Metric | ollama | claude |" in table
    assert "| numeric_accuracy | 0.900 | 1.000 |" in table
    assert "| point_in_time_leaks | 0 | – |" in table
