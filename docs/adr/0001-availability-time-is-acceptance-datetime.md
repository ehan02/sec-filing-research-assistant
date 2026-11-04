# Availability Time is the EDGAR acceptance datetime

Point-in-time filtering compares As-of against each Filing's acceptance datetime (US Eastern), not its `filingDate`, and Facts inherit that time by joining their accession number to the Filing. `filingDate` rolls filings accepted after 17:30 ET to the next business day, and companyfacts' `filed` field has no time at all, so either one would misplace after-hours 8-K earnings releases by a day. For Quant-mode features joined to returns, that is look-ahead or look-behind bias.

## Consequences

- The numbers pipeline cannot be loaded from companyfacts alone. It needs the submissions list to look up each Fact's Availability Time, and a Fact whose accession number isn't in that list cannot be used.
- A date-only As-of means the end of that day, US Eastern time.
