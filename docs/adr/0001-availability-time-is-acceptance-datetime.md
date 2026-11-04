# Availability Time is the EDGAR acceptance datetime

Point-in-time filtering compares As-of against each Filing's acceptance datetime (US Eastern), not its `filingDate`, and Facts inherit that time by joining their accession number to the Filing. `filingDate` rolls filings accepted after 17:30 ET to the next business day, and companyfacts' `filed` field has no time at all, so either one would misplace after-hours 8-K earnings releases by a day. For Quant-mode features joined to returns, that is look-ahead or look-behind bias.

## Consequences

- The numbers pipeline cannot be loaded from companyfacts alone. It needs the submissions list to look up each Fact's Availability Time, and a Fact whose accession number isn't in that list cannot be used.
- A date-only As-of means the end of that day, US Eastern time.
- The submissions API's `acceptanceDateTime` suffix `Z` is genuine UTC and is converted to US Eastern. This was verified on 2026-11-03 against EDGAR index pages: AAPL 8-K 0000320193-26-000024 reads `21:30:23Z` and its index page shows "Accepted 16:30:23" (EST); 0000320193-26-000018 reads `20:30:28Z` and its index page shows 16:30:28 (EDT).
