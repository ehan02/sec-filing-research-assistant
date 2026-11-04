# 14: Demo Universe run

**What to build:** The whole pipeline runs on a real Universe of 10–20 Companies over 3–5 years. The result is a reproducible demo:
- evaluation scores for each configuration;
- sample cited answers to the README example questions;
- a `features.parquet` with a cross-sectional Item 1A similarity ranking.

**Blocked by:** 11 (Batch feature job), 13 (Eval: answer quality and model comparison)

**Status:** ready-for-agent

- [ ] The Universe's Tickers and date window are fixed in a versioned config.
- [ ] One documented sequence of commands downloads, indexes, loads Facts, runs the evaluation sets and the feature job, starting from an empty data directory.
- [ ] Sample answers to all ten README example questions are captured with their Citations.
- [ ] The README's Roadmap and Status are updated to reflect what is done. The README states that the demo shows the pipeline works, not that the signal does.
