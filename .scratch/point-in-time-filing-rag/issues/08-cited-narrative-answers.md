# 08: Cited narrative answers

**What to build:** An analyst asks a narrative question and gets a prose answer in which every claim carries a Citation to a retrieved Chunk. If nothing relevant is retrieved, they get the Abstention sentence. Answers whose Citations don't match what was retrieved are rejected and regenerated, so every Citation the analyst sees is real.

**Blocked by:** 03 (Text tracer: `filing_search` over 10-K Sections (BM25))

**Status:** ready-for-agent

- [x] The chat model is an injected dependency, chosen by config (Ollama or Claude). Tests inject a fake model that returns scripted answers.
- [x] The prompt wraps retrieved context in `<documents>` tags marked as data, requires a Citation for every claim, and specifies the exact Abstention sentence: "The filings provided do not contain this information."
- [x] Citations use the spec's formats: 10-K, 10-Q Part/Item, 8-K exhibit, and the `/A` form for Amendments.
- [x] A post-check parses every Citation and requires each to match a retrieved Chunk's accession number and Section. On failure the answer is regenerated, up to a fixed number of times, then replaced by the Abstention sentence.
- [x] Tests with the fake model:
  - a Citation to an unretrieved accession number triggers regeneration;
  - repeated failures end in the exact Abstention sentence;
  - context arrives inside `<documents>` tags;
  - an answer with valid Citations passes unchanged.

## Comments

**Done (2026-11-04).**
- **Injected model:** a plain function `chat(system, messages) -> str`, not a LangChain chat model, so tests pass a scripted function. `chat_model()` builds one from `DEFAULT_LLM`:
  - Ollama goes through `langchain-ollama`, at temperature 0.
  - Claude goes through the official `anthropic` SDK: `ANTHROPIC_MODEL`, default `claude-opus-5-5`, effort `medium`. Server-side refusal fallbacks (`fallbacks: "default"`) are on, and a final refusal becomes the Abstention sentence.
- **Context:** each Chunk is a `<document citation="…">` inside `<documents>`, with its text HTML-escaped so filing text can't close the tags. The system prompt marks the documents as data, never instructions.
- **Post-check:** every bracketed citation must match a retrieved Chunk's citation exactly, and an answer with no citations is rejected too. A failed answer is sent back with the problem named. After 3 attempts in total, the answer becomes the Abstention sentence. If nothing is retrieved, the result is an abstention without calling the model.
- **Real-model check, local `llama3.2` (3B) on real AAPL filings.** The first attempt failed when Ollama ran out of memory; it worked after other apps were closed. `qwen2.5:7b` (the `.env` default) isn't pulled, and Claude is untested because `ANTHROPIC_API_KEY` is empty.
  - Single-source suppliers (latest 10-K as of 2025-06-30): passed on the 2nd attempt, after the post-check rejected the first. Cited `[AAPL 10-K FY2024 Item 8, 0000320193-24-000123]`, and the cited Chunk contains the quoted "custom components available from only one source" passage. The answer is mostly copied text. 94 s.
  - Latest dividend: "$0.27 per share" `[AAPL 8-K Ex-99.1, 0000320193-26-000024]`, matching the release, on the 1st attempt. 61 s.
  - FY2028 revenue guidance: returned the exact Abstention sentence. 46 s.
  - The post-check proves each citation was retrieved, not that the claim comes from it; checking that is ticket 13's faithfulness score.
