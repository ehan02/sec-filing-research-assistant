# 13: Eval: answer quality and model comparison

**What to build:** A researcher can measure end-to-end answer quality and compare configurations on equal terms:
- citation validity, faithfulness and correct-decline rate, across the narrative, numeric, point-in-time and Abstention sets;
- Ollama vs Claude;
- embedding model A vs B.

**Blocked by:** 06 (Retrieval eval: narrative set, Recall@5), 10 (Router agent and SKILL.md), 12 (Eval: numeric and point-in-time sets)

**Status:** ready-for-agent

- [x] An Abstention set of questions that have no answer in the filings (seeded with README example 10) is scored by correct-decline rate.
- [x] Narrative answers are scored for citation validity (every Citation matches a real Chunk) and faithfulness (claims are supported by the cited text).
- [x] The numeric and point-in-time sets from ticket 12 run end-to-end through the router.
- [x] One command runs every set under a named configuration (LLM provider, embedding model) and writes a side-by-side comparison report.

## Comments

**Done (2026-11-04).**
- **One command per configuration:** `python -m tests.eval_filings all --llm ollama|anthropic [--judge-llm …] [--limit N] [--db …] --label NAME` runs every set through the router and writes `data/eval/all-NAME.json` with a `metrics` block and the config (LLM and model, judge, `EMBED_MODEL`, `RERANK_MODEL`, index, limit, tolerance). To compare embedding models, build a second index with another `EMBED_MODEL` and pass it with `--db`. `python -m tests.eval_filings compare NAME1 NAME2 …` writes the side-by-side table to `data/eval/comparison.md`.
- **Sets and metrics:**
  - Narrative: Recall@5 as in ticket 06, plus end-to-end answers scored for citation validity (every Citation names a real Chunk's Filing and Section, or a real Fact) and faithfulness (a judge model, by default the answering one, says yes/no for each cited sentence against the cited text).
  - Numeric and point-in-time (ticket 12): asked through the router at each question's exact As-of (passed to `ask`, so the 1-second-before questions stay exact), and scored on the stated number closest to the expected value.
  - Abstention: `tests/eval/abstention.json`, 8 questions including README example 10 adapted to AAPL; scored by correct-decline rate.
  - `--limit N` samples N questions per set evenly (N Restatement pairs for point-in-time).
- **Answers now carry `sources`:** citation → the text it labeled in the prompt, parsed from the `<document>`/`<fact>` blocks. The judge uses it, and the router merges it across Companies.
- **Real run, `llama3.2`, `--limit 2`** (8.2 GB free commit memory, 9 min): Recall@5 0.868; abstention 1.000; numeric 0/2, point-in-time 0/4 (0 leaks), and both narrative answers abstained, so validity and faithfulness have nothing to score. All of these abstained because the 3B model doesn't follow the plan format: it nests the tool arguments (`"numeric": {"concepts": …}`), routes everything as `combined`, puts `"FY2012 Q2"` into `fiscal_year`, and invents `section` filters. So there were no Facts and no Chunks, and the router abstained without calling the model. The perfect abstention score is therefore not evidence of good declining. Claude is untested (`ANTHROPIC_API_KEY` is empty).
- **Not verified:** one sampled point-in-time "Restatement" is AAPL `AccountsPayableCurrent` FY2017 (49,049M → 44,242M). It may be two instants mapped to the same Fiscal Period rather than a real Restatement.

**Plan hardening (2026-11-04).** Prompted by that run, the router's plan node (`_normalize` in `src/agents/nodes.py`) now:
- flattens arguments nested under another key;
- turns a bare Ticker string into a list;
- reads fiscal years as ints (`"FY2023"` → 2023; anything else, like `"FY2012 Q2"`, is dropped);
- for narrative and combined searches, keeps `section` and `fiscal_year` only when the question names them.

Re-run, same settings (`--limit 2`, 12.1 GB free, 10 min), `compare ollama-llama3.2 ollama-llama3.2-hardened`:

| Metric | before | hardened |
|---|---|---|
| narrative_recall_at_5 | 0.868 | 0.868 |
| narrative_citation_validity | – | 1.000 |
| narrative_faithfulness | – | 0.000 |
| numeric_accuracy | 0.000 | 0.500 |
| point_in_time_accuracy | 0.000 | 0.750 |
| point_in_time_leaks | 0 | 0 |
| abstention_correct_decline_rate | 1.000 | 1.000 |

Two of the remaining misses were scorer bugs, fixed afterwards (not re-run yet):
- The number reader dropped minus signs, so the right answer "-289,000,000" read back as +289M. `router_lookup` now keeps the sign.
- Faithfulness split sentences only at `. `, so a bulleted list was judged as one claim (and rejected). Each line is now its own claim.

The other numeric miss (AAPL Assets FY2008) gave no number; it isn't diagnosed yet.
