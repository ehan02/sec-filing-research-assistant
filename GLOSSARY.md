# SEC Filing Research Assistant

A local research assistant that answers questions about companies' SEC filings with cited, point-in-time answers. It also extracts dated text features for backtests.

## Identity

**Company**:
A registrant with SEC filings, identified by its CIK.
_Avoid_: Ticker (as an identifier), issuer, firm

**Ticker**:
Today's trading symbol for a Company. It is used to name a Company in questions and answers, never to identify one. Historical tickers are not tracked.
_Avoid_: Symbol

**Filing**:
One submission to EDGAR, identified by its accession number. It holds a primary document plus, for an 8-K, its Exhibit 99 documents.
_Avoid_: Report, document (for the whole submission)

**Amendment**:
A Filing whose form ends in `/A` (10-K/A, 10-Q/A, 8-K/A). It is a Filing in its own right, never a replacement for the Original it amends.

**Original**:
A Filing that is not an Amendment. "The latest 10-K" always means the latest Original 10-K.

## Time

**Availability Time**:
The moment a Filing became public: its EDGAR acceptance datetime, in US Eastern time. A Fact inherits the Availability Time of the Filing that reported it.
_Avoid_: Filing date (for this meaning), publish date

**As-of**:
A point in time the user asks the question from. Only Filings and Facts whose Availability Time is at or before it may be used. A date with no time means the end of that day, US Eastern time.
_Avoid_: Cutoff, snapshot date

**Fiscal Year**:
The Company's fiscal year that a reported period falls in. It never means the fiscal year of the Filing that reported a value.
_Avoid_: `fy` (the raw XBRL field)

**Fiscal Period**:
A quarter (Q1–Q4) or the full year (FY) within a Fiscal Year, again always describing the reported period.

## Content

**Section**:
A form-aware part of a Filing: an Item of a 10-K (e.g. `Item 1A`), a Part and Item of a 10-Q (e.g. `Part I Item 2`), or an 8-K exhibit (e.g. `Ex-99.1`).
_Avoid_: Item (on its own, for 10-Qs and exhibits), chapter

**Chunk**:
A contiguous span of text from one Section, never crossing a Section boundary. A table and its caption always form one whole Chunk.
_Avoid_: Passage, snippet

**Fact**:
One XBRL value a Filing reported for a Company: a concept, unit, period and value.
_Avoid_: Metric, data point

**Restatement**:
A later Filing reporting a different value for the same Company, concept, unit and period. A later Filing that repeats the same value is a comparative, not a Restatement.

**Citation**:
A pointer from a claim in an answer to the Chunk or Fact that supports it, naming the Filing by accession number.
_Avoid_: Reference, source (for this meaning)

**Abstention**:
An answer that declines because the available Filings don't contain the information.
_Avoid_: Refusal

## Research

**Universe**:
The fixed list of Companies the assistant has downloaded and indexed.

**Section Diff**:
A comparison of the same Section across two Filings of the same form: a similarity score plus added, removed and reworded paragraphs.
_Avoid_: Redline, change report
