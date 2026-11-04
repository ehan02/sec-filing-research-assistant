# 01: Downloader: amendments, Availability Time, fixture Universe

**What to build:** Downloading a Universe also fetches each form's Amendments (10-K/A, 10-Q/A, 8-K/A), and every saved Filing records its Availability Time (ADR-0001). Later stages can look up any accession number's Availability Time, and one shared function turns any As-of input into an Eastern-time datetime. Tests get a reusable fixture Universe built on the existing fake EDGAR client, so every later ticket can build a small corpus offline. This is the prefactor every other ticket stands on.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] Asking for `10-K` (or the default forms) also selects `10-K/A`, and likewise for 10-Q and 8-K. An Amendment is saved as its own Filing under its own accession number.
- [x] Saved Filing metadata includes `availability_time` (US Eastern, timezone-aware) and `is_amendment`.
- [x] Whether `acceptanceDateTime` is really UTC or US Eastern with a misleading `Z` is checked against a known after-hours 8-K. The finding is recorded in ADR-0001 and the conversion is implemented to match.
- [x] The downloader exposes an accession number → Availability Time lookup built from the cached submissions lists.
- [x] One shared As-of normalizer: a datetime passes through as Eastern time, a date-only value becomes the end of that day Eastern, and an omitted value means now. No other module parses As-of strings.
- [x] A reusable test fixture builds a small Universe through the fake EDGAR. It includes a 10-K, a 10-Q, an 8-K with Ex-99.1 accepted after 17:30 ET, a Part III-only 10-K/A, and a companyfacts file.
- [x] Existing downloader tests still pass, and new tests cover Amendment selection, Availability Time and As-of normalization (one minute before/after acceptance, date-only on the acceptance day).

## Comments

**Done (2026-11-03).**
- The `acceptanceDateTime` `Z` is genuine UTC, verified against two AAPL 8-K index pages; recorded in ADR-0001.
- Availability Time and the As-of normalizer live in one new module next to the downloader.
- The downloader selects `/A` forms, saves `availability_time` and `is_amendment` in each filing's metadata, and exposes `availability_times(ticker)` across the full submissions history and all forms.
- The fixture Universe (fictional Fixture Corp, `FIXT`) is a `universe` pytest fixture. Its contents are documented in the fixture module's docstring.
- It also covers the facts cases ticket 02 needs: an identical comparative, a Restatement, a Fiscal Year mismatch, and a fact with an unknown accession number.
- Added `tzdata` to requirements, because Windows has no system time zone database.
