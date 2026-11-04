# 08: Cited narrative answers

**What to build:** An analyst asks a narrative question and gets a prose answer in which every claim carries a Citation to a retrieved Chunk. If nothing relevant is retrieved, they get the Abstention sentence. Answers whose Citations don't match what was retrieved are rejected and regenerated, so every Citation the analyst sees is real.

**Blocked by:** 03 (Text tracer: `filing_search` over 10-K Sections (BM25))

**Status:** ready-for-agent

- [ ] The chat model is an injected dependency, chosen by config (Ollama or Claude). Tests inject a fake model that returns scripted answers.
- [ ] The prompt wraps retrieved context in `<documents>` tags marked as data, requires a Citation for every claim, and specifies the exact Abstention sentence: "The filings provided do not contain this information."
- [ ] Citations use the spec's formats: 10-K, 10-Q Part/Item, 8-K exhibit, and the `/A` form for Amendments.
- [ ] A post-check parses every Citation and requires each to match a retrieved Chunk's accession number and Section. On failure the answer is regenerated, up to a fixed number of times, then replaced by the Abstention sentence.
- [ ] Tests with the fake model:
  - a Citation to an unretrieved accession number triggers regeneration;
  - repeated failures end in the exact Abstention sentence;
  - context arrives inside `<documents>` tags;
  - an answer with valid Citations passes unchanged.
