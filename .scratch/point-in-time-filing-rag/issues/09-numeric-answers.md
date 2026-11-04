# 09: Numeric answers

**What to build:** An analyst asks a financial question ("AAPL revenue and gross margin FY2020–FY2024") and gets exact numbers. They come from `get_financials`, any arithmetic is done in Python, and the model only narrates them. Every number carries a Fact Citation.

**Blocked by:** 02 (Facts tracer: `get_financials` as-of), 08 (Cited narrative answers)

**Status:** done

- [x] Derived values (margins, growth, differences) are computed in Python from `get_financials` output and passed to the model as given numbers. The model never performs arithmetic.
- [x] Fact Citations use the format `[TICKER concept FYyyyy, accession]`, with the period's Fiscal Year and the reporting Filing's accession number.
- [x] The post-check from ticket 08 also validates Fact Citations against the Facts returned, and rejects any number in the answer that isn't among the given values.
- [x] A missing Fact for a requested period is stated as unavailable, not estimated.
- [x] Tests with the fake model:
  - the numbers passed to the model match Python's computation;
  - a scripted answer containing a number that wasn't given is rejected;
  - FY labels in Citations are the period's, not the Filing's.

## Comments

**Done (2026-11-04).**
- **Entry point:** `answer_financials(question, chat, ticker, concepts, periods, as_of, ratios=…)` in `src/rag/answer.py`. Choosing concepts, periods and ratios from the question is the router's job (ticket 10).
- **Derived values, in Python:** each concept's change between consecutive `periods` (absolute and %), and each `ratios` entry `name: (numerator, denominator)` as a % per period. Values whose inputs are missing are skipped.
- **Context:** `<fact citation="…">` lines inside `<facts>`; a missing Fact is `<fact>concept period: unavailable</fact>` with no citation. A derived value carries the citations of its inputs. If no Fact is available at all, the result is an abstention without calling the model.
- **Post-check:** ticket 08's retry loop is now shared (`_generate`). For numeric answers it also rejects any standalone number not among the given values (digits inside labels like `FY2023` or `Q1` don't count, and citations are ignored). So the model must copy numbers as given: "1.2 billion" for `1,200,000,000 USD` is rejected.
- **Real AAPL data (Python side only):** revenue (`RevenueFromContractWithCustomerExcludingAssessedTax`) and gross profit FY2020–FY2024 give revenue $274,515M → $391,035M and gross margin 38.2%, 41.8%, 43.3%, 44.1%, 46.2%, matching Apple's 10-Ks. A Fact cites the latest Filing that reported it at the As-of, so FY2020 cites the FY2022 10-K's comparative.
- **Real-model check, local `llama3.2` (3B) on real AAPL Facts** (11.4 GB free commit memory, no search models loaded). Every number it stated was exact and correctly cited, and the post-check rejected one bad first attempt. But the answers were incomplete:
  - Revenue and gross margin FY2020–FY2024: passed on the 2nd attempt, 361 s. It listed all five revenues, copying the raw fact lines, but left out the gross margins it was given and ended with the Abstention sentence.
  - Revenue and net income FY2024–FY2025 as of 2025-06-30: FY2024 revenue $391,035M and net income $93,736M, cited to the FY2024 10-K, on the 1st attempt, 37 s. FY2025 wasn't public yet; the model didn't estimate it but ended with the Abstention sentence instead of saying "unavailable".
  - Net margin FY2025 Q1: 29.2%, correct, citing both inputs (inside a "[derived from …]" wrapper the citation regex still accepts), 1st attempt, 60 s.
  - The post-check can't catch an omitted value or an Abstention sentence tacked onto a real answer; completeness is for ticket 13's answer-quality eval. Claude is still untested (`ANTHROPIC_API_KEY` is empty).

**Stricter post-check (2026-11-04, `14ea422`).** The answer must now contain every requested ratio and say "unavailable" for each missing Fact, and an Abstention sentence tacked onto a real answer is dropped. Re-run of the same three `llama3.2` questions:
- Revenue and gross margin FY2020–FY2024: abstained after 3 attempts, 542 s. It still left out the margins, and now it's rejected instead of accepted as a partial answer.
- Revenue and net income FY2024–FY2025 as of 2025-06-30: passed on the 2nd attempt, 111 s. It gave the FY2024 values and now calls both FY2025 values "unavailable".
- Net margin FY2025 Q1: 29.2%, 1st attempt, 35 s.
