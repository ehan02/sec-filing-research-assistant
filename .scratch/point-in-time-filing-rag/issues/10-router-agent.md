# 10: Router agent and SKILL.md

**What to build:** An analyst asks any question in plain language and the assistant picks the right path:
- narrative → `filing_search`;
- numeric → `get_financials` plus Python;
- change → `section_diff`;
- combined → numbers and narrative together;
- not in the filings → Abstention.

Questions across the whole Universe ("did any company report a material weakness?") fan out over every Company.

**Blocked by:** 05 (10-Q, 8-K exhibits and Amendments in search), 07 (`section_diff` tool), 09 (Numeric answers)

**Status:** ready-for-agent

- [ ] A LangGraph router classifies the question and calls the matching tools, always passing an explicit As-of (now, if the user gave none).
- [ ] Combined questions produce one answer that explains the numbers and the narrative together, with both kinds of Citation.
- [ ] Universe-wide questions run the relevant tool per Company and report per-Company results with Citations.
- [ ] Questions about the future or about information that isn't in the filings end in the Abstention sentence.
- [ ] The `filing-research` skill file's routing table and rules match the router's behavior.
- [ ] Tests with the fake model drive one question of each type through the router, and assert which tools were called and with what As-of.
