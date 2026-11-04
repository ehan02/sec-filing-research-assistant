# 13: Eval: answer quality and model comparison

**What to build:** A researcher can measure end-to-end answer quality and compare configurations on equal terms:
- citation validity, faithfulness and correct-decline rate, across the narrative, numeric, point-in-time and Abstention sets;
- Ollama vs Claude;
- embedding model A vs B.

**Blocked by:** 06 (Retrieval eval: narrative set, Recall@5), 10 (Router agent and SKILL.md), 12 (Eval: numeric and point-in-time sets)

**Status:** ready-for-agent

- [ ] An Abstention set of questions that have no answer in the filings (seeded with README example 10) is scored by correct-decline rate.
- [ ] Narrative answers are scored for citation validity (every Citation matches a real Chunk) and faithfulness (claims are supported by the cited text).
- [ ] The numeric and point-in-time sets from ticket 12 run end-to-end through the router.
- [ ] One command runs every set under a named configuration (LLM provider, embedding model) and writes a side-by-side comparison report.
