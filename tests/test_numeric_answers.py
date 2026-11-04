"""Numeric answers from Facts with a scripted chat model, over the fixture Universe."""

from __future__ import annotations

import pytest

from src.filings.xbrl import load_facts
from src.rag.answer import ABSTAIN, answer_financials
from tests import fixture_universe as fu
from tests.fakes import ScriptedChat

REVENUE = "us-gaap:Revenues"
NET_INCOME = "us-gaap:NetIncomeLoss"
# FY2022 revenue as repeated by the FY2023 10-K: the period's year, the reporting Filing's accession.
REV_2022 = f"FIXT {REVENUE} FY2022, {fu.ACC_10K_2023}"
REV_2023 = f"FIXT {REVENUE} FY2023, {fu.ACC_10K_2023}"
QUESTION = "What were Fixture Corp's revenue and net margin?"


@pytest.fixture
def db(universe, tmp_path):
    path = tmp_path / "facts.db"
    load_facts(universe.downloader, fu.TICKER, path)
    return path


def _ask(universe, db, chat, concepts=(REVENUE, NET_INCOME), periods=("FY2022", "FY2023"),
         as_of="2024-06-01", **kw):
    return answer_financials(QUESTION, chat, "fixt", list(concepts), list(periods), as_of,
                             downloader=universe.downloader, db_path=db, **kw)


def _given(chat):
    return chat.calls[0][1][0]["content"]


def test_derived_values_are_computed_in_python_and_given_to_the_model(universe, db):
    good = f"FY2023 revenue was 1,200,000,000 USD, up 20.0% [{REV_2023}]."
    chat = ScriptedChat(good)
    result = _ask(universe, db, chat, ratios={"net margin": (NET_INCOME, REVENUE)})

    assert result == {"answer": good, "citations": [REV_2023], "attempts": 1, "abstained": False}
    given = _given(chat)
    for line in [
        f'<fact citation="{REV_2022}">{REVENUE} FY2022: 1,000,000,000 USD</fact>',
        f"{REVENUE} change FY2022 to FY2023: +200,000,000 USD (+20.0%)",
        f"{NET_INCOME} change FY2022 to FY2023: +60,000,000 USD (+66.7%)",
        "net margin FY2022: 9.0%",
        "net margin FY2023: 12.5%",
    ]:
        assert line in given
    assert "never calculate" in chat.calls[0][0]


def test_answer_with_a_number_that_was_not_given_is_rejected(universe, db):
    bad = f"FY2023 revenue was 1,250,000,000 USD [{REV_2023}]."
    good = f"FY2023 revenue was 1,200,000,000 USD [{REV_2023}]."
    chat = ScriptedChat(bad, good)
    result = _ask(universe, db, chat)

    assert (result["answer"], result["attempts"]) == (good, 2)
    retry = chat.calls[1][1][2]["content"]
    assert "rejected" in retry and "1,250,000,000" in retry


def test_fact_citation_names_the_periods_fiscal_year_not_the_filings(universe, db):
    filing_year = f"FIXT {REVENUE} FY2023, {fu.ACC_10K_2022}"
    good = f"FY2022 revenue was 1,000,000,000 USD [{REV_2022}]."
    chat = ScriptedChat(f"FY2022 revenue was 1,000,000,000 USD [{filing_year}].", good)
    result = _ask(universe, db, chat)

    assert (result["citations"], result["attempts"]) == ([REV_2022], 2)
    assert f'citation="{REV_2022}"' in _given(chat)


def test_missing_fact_is_given_as_unavailable(universe, db):
    good = f"FY2023 revenue was 1,200,000,000 USD [{REV_2023}]. FY2024 Q1 revenue is unavailable."
    chat = ScriptedChat(good)
    result = _ask(universe, db, chat, concepts=[REVENUE], periods=["FY2023", "FY2024 Q1"],
                  as_of="2024-05-01T16:09")

    assert (result["answer"], result["attempts"]) == (good, 1)
    given = _given(chat)
    assert f"<fact>{REVENUE} FY2024 Q1: unavailable</fact>" in given
    assert "change FY2023 to FY2024 Q1" not in given


def test_no_facts_at_the_as_of_abstains_without_calling_the_model(universe, db):
    chat = ScriptedChat()
    result = _ask(universe, db, chat, as_of="2020-01-01")
    assert result == {"answer": ABSTAIN, "citations": [], "attempts": 0, "abstained": True}
    assert chat.calls == []
