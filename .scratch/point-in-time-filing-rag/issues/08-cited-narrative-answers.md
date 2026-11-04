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

**Done (2026-11-04); not yet run against a real model.**
- **Injected model:** a plain function `chat(system, messages) -> str`, not a LangChain chat model, so tests pass a scripted function. `chat_model()` builds one from `DEFAULT_LLM`:
  - Ollama goes through `langchain-ollama`, at temperature 0.
  - Claude goes through the official `anthropic` SDK: `ANTHROPIC_MODEL`, default `claude-opus-5-5`, effort `medium`. Server-side refusal fallbacks (`fallbacks: "default"`) are on, and a final refusal becomes the Abstention sentence.
- **Context:** each Chunk is a `<document citation="…">` inside `<documents>`, with its text HTML-escaped so filing text can't close the tags. The system prompt marks the documents as data, never instructions.
- **Post-check:** every bracketed citation must match a retrieved Chunk's citation exactly, and an answer with no citations is rejected too. A failed answer is sent back with the problem named. After 3 attempts in total, the answer becomes the Abstention sentence. If nothing is retrieved, the result is an abstention without calling the model.
- **Real-model check blocked by memory.** Ollama couldn't allocate a 650 MB buffer to load `llama3.2` while the embedder and reranker were loaded on this 7.7 GB machine. `qwen2.5:7b` (the `.env` default) isn't pulled, and `ANTHROPIC_API_KEY` is empty. Re-run with more free memory, or with a key.
