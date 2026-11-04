# 10: Router agent and SKILL.md

**What to build:** An analyst asks any question in plain language and the assistant picks the right path:
- narrative → `filing_search`;
- numeric → `get_financials` plus Python;
- change → `section_diff`;
- combined → numbers and narrative together;
- not in the filings → Abstention.

Questions across the whole Universe ("did any company report a material weakness?") fan out over every Company.

**Blocked by:** 05 (10-Q, 8-K exhibits and Amendments in search), 07 (`section_diff` tool), 09 (Numeric answers)

**Status:** done

- [x] A LangGraph router classifies the question and calls the matching tools, always passing an explicit As-of (now, if the user gave none).
- [x] Combined questions produce one answer that explains the numbers and the narrative together, with both kinds of Citation.
- [x] Universe-wide questions run the relevant tool per Company and report per-Company results with Citations.
- [x] Questions about the future or about information that isn't in the filings end in the Abstention sentence.
- [x] The `filing-research` skill file's routing table and rules match the router's behavior.
- [x] Tests with the fake model drive one question of each type through the router, and assert which tools were called and with what As-of.

## Comments

**Done (2026-11-04).**
- **Graph** (`src/agents/agent.py`): `START → plan →` one of `narrative | numeric | change | combined | abstain` `→ END`. `ask(question, chat, as_of=None)` returns the answer, Citations, `abstained`, `route`, the `as_of` used, and `per_company`.
- **Plan node** (`src/agents/nodes.py`): the chat model replies with a JSON plan (route, tickers or `["*"]`, as_of, and the route's tool arguments). A reply that isn't a valid plan becomes an abstention. The As-of is the caller's, else the question's, else now, always passed to tools as an explicit Eastern datetime.
- **Routes:** each runs its tools per Company and hands the output to a generator in `src/rag/answer.py`. Generation was split from retrieval for this: `answer_from_chunks`, `answer_from_facts`, the new `answer_from_diff` (added/removed/reworded paragraphs cited to the later/earlier Filing, plus the similarity score), and `answer_combined` (`<facts>` and `<documents>` in one prompt, both kinds of Citation allowed, numbers allowed from the Facts or the Chunks' text). `answer_question` and `answer_financials` are now thin wrappers.
- **Universe-wide:** `["*"]` expands to every Company with saved Filings. Each gets its own result in `per_company`, and the answer lists them as `TICKER: answer`.
- **Abstention:** the `abstain` route (the future, guidance, anything not in filings) calls no tools. A `section_diff` error (Filing missing or not yet public) also ends in the Abstention sentence.
- **Skill file:** `skills/filing-research/SKILL.md` has the five-route table, the Universe-wide rule, and the future/unavailable rules.
- **Tests** (`tests/test_router.py`, scripted model): one question per route, asserting the tools called, their arguments and As-of, and the answer's Citations; plus an unparsable plan. The fixture Universe has one Company, so fan-out is only tested with one Company.
