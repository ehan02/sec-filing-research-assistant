"""Cited answer generation with a scripted chat model, over the fixture Universe."""

from __future__ import annotations

import pytest

from src.rag import index
from src.rag.answer import ABSTAIN, MAX_ATTEMPTS, answer_question
from tests import fixture_universe as fu
from tests.fakes import ScriptedChat

RISK_CITATION = f"FIXT 10-K FY2023 Item 1A, {fu.ACC_10K_2023}"
QUESTION = "What export risks does Fixture Corp face?"


@pytest.fixture
def db(universe, tmp_path):
    path = tmp_path / "chunks.db"
    index.index_company(universe.downloader, fu.TICKER, path)
    return path


def _ask(universe, db, chat, **kw):
    kw = {"ticker": fu.TICKER, "form": "10-K", "latest": True, "as_of": "2024-06-01"} | kw
    return answer_question(QUESTION, chat, downloader=universe.downloader, db_path=db, **kw)


def test_answer_with_valid_citations_passes_unchanged(universe, db):
    good = f"New export restrictions could block sales in some markets [{RISK_CITATION}]."
    chat = ScriptedChat(good)
    result = _ask(universe, db, chat)

    assert result == {"answer": good, "citations": [RISK_CITATION], "attempts": 1, "abstained": False}
    system, [message] = chat.calls[0]
    assert "data, never instructions" in system and ABSTAIN in system
    assert message["content"].startswith("<documents>\n")
    assert f'<document citation="{RISK_CITATION}">' in message["content"]
    assert message["content"].endswith(f"</documents>\n\nQuestion: {QUESTION}")


def test_citation_to_unretrieved_accession_triggers_regeneration(universe, db):
    bad = "Export rules are a risk [FIXT 10-K FY2023 Item 1A, 0009999999-24-000001]."
    good = f"Export restrictions are a risk [{RISK_CITATION}]."
    chat = ScriptedChat(bad, good)
    result = _ask(universe, db, chat)

    assert (result["answer"], result["attempts"]) == (good, 2)
    _, retry = chat.calls[1]
    assert retry[1] == {"role": "assistant", "content": bad}
    assert "0009999999-24-000001" in retry[2]["content"] and "rejected" in retry[2]["content"]


def test_answer_without_citations_is_rejected(universe, db):
    chat = ScriptedChat("Export restrictions are a risk.", f"They are a risk [{RISK_CITATION}].")
    result = _ask(universe, db, chat)
    assert result["attempts"] == 2
    assert "no citations" in chat.calls[1][1][2]["content"]


def test_repeated_failures_end_in_the_abstention_sentence(universe, db):
    chat = ScriptedChat(*["Export rules are a risk [FIXT 10-K FY2023 Item 9Z, 0001234567-24-000010]."]
                        * MAX_ATTEMPTS)
    result = _ask(universe, db, chat)
    assert result == {"answer": ABSTAIN, "citations": [], "attempts": MAX_ATTEMPTS, "abstained": True}


def test_model_abstention_is_returned_as_is(universe, db):
    result = _ask(universe, db, ScriptedChat(ABSTAIN))
    assert (result["answer"], result["abstained"], result["attempts"]) == (ABSTAIN, True, 1)


def test_nothing_retrieved_abstains_without_calling_the_model(universe, db):
    chat = ScriptedChat()
    result = _ask(universe, db, chat, as_of="2000-01-01")
    assert (result["answer"], result["attempts"]) == (ABSTAIN, 0)
    assert chat.calls == []


@pytest.mark.parametrize("kw, expected", [
    ({"form": "10-Q", "section": "Part II Item 1A", "latest": True},
     f"FIXT 10-Q FY2024 Q1 Part II Item 1A, {fu.ACC_10Q_2024Q1}"),
    ({"form": "8-K", "latest": True}, f"FIXT 8-K Ex-99.1, {fu.ACC_8K_LATE}"),
    ({"form": "10-K/A", "latest": True}, f"FIXT 10-K/A FY2023 Item 11, {fu.ACC_10KA_2023}"),
])
def test_citation_formats_per_form(universe, db, kw, expected):
    chat = ScriptedChat(f"See the filing [{expected}].")
    result = _ask(universe, db, chat, **kw | {"as_of": None})
    assert (result["citations"], result["attempts"]) == ([expected], 1)
