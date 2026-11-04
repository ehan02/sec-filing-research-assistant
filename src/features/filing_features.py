"""Batch text features: one row per Company × Original 10-K, written to features.parquet.

Each row compares Item 1A and Item 7 with the prior Original 10-K that was
public at this Filing's own Availability Time, so no row uses a later Filing.
Keyed by ``(cik, accession_no, availability_time)``. Run with
``python -m src.features.filing_features``.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.filings.diff import diff_paragraphs
from src.filings.edgar import ROOT, EdgarClient, EdgarDownloader
from src.filings.parse import parse_sections
from src.filings.xbrl import fiscal_year

FEATURES = ROOT / "data" / "features.parquet"
SECTIONS = ("Item 1A", "Item 7")


def build_features(downloader: EdgarDownloader) -> pd.DataFrame:
    """Feature rows for every saved Original 10-K, ordered by CIK and Availability Time."""
    rows = []
    for company in sorted(downloader.filings_dir.glob("*"), key=lambda p: p.name):
        filings = []
        for path in company.glob("*/metadata.json"):
            meta = json.loads(path.read_text(encoding="utf-8"))
            if meta["form"] == "10-K":
                sections = {s["section"]: s["blocks"]
                            for s in parse_sections((path.parent / meta["primary_document"]).read_bytes(), "10-K")}
                filings.append((datetime.fromisoformat(meta["availability_time"]), meta, sections))
        if not filings:
            continue
        cik = filings[0][1]["cik"]
        sub_path = downloader.cache_dir / "submissions" / f"CIK{cik:010d}.json"
        fye = json.loads(sub_path.read_text(encoding="utf-8"))["fiscalYearEnd"]

        filings.sort(key=lambda f: (f[0], f[1]["accession_no"]))
        for i, (available, meta, sections) in enumerate(filings):
            prior = filings[i - 1] if i else None  # sorted, so it was public before this one
            row = {"cik": cik, "ticker": meta["ticker"], "accession_no": meta["accession_no"],
                   "availability_time": available,
                   "fiscal_year": fiscal_year(date.fromisoformat(meta["report_date"]), fye),
                   "prior_accession_no": prior[1]["accession_no"] if prior else None}
            for name in SECTIONS:
                col = name.lower().replace(" ", "_")
                now = _paragraphs(sections, name)
                before = _paragraphs(prior[2], name) if prior else None
                row[f"{col}_similarity"] = (diff_paragraphs(before, now)["similarity"]
                                            if now is not None and before is not None else None)
                row[f"{col}_words"] = sum(len(p.split()) for p in now) if now is not None else None
            count = _risk_factor_count(sections)
            prior_count = _risk_factor_count(prior[2]) if prior else None
            row["risk_factor_count"] = count
            row["risk_factor_count_change"] = (count - prior_count
                                               if count is not None and prior_count is not None else None)
            rows.append(row)

    df = pd.DataFrame(rows, columns=[
        "cik", "ticker", "accession_no", "availability_time", "fiscal_year", "prior_accession_no",
        "item_1a_similarity", "item_1a_words", "item_7_similarity", "item_7_words",
        "risk_factor_count", "risk_factor_count_change"])
    for col in ("item_1a_words", "item_7_words", "risk_factor_count", "risk_factor_count_change"):
        df[col] = df[col].astype("Int64")
    for col in ("item_1a_similarity", "item_7_similarity"):
        df[col] = df[col].astype("float64")
    return df


def write_features(downloader: EdgarDownloader, path: Path = FEATURES) -> pd.DataFrame:
    df = build_features(downloader)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def _paragraphs(sections: dict[str, list[dict]], name: str) -> list[str] | None:
    return [b["text"] for b in sections[name]] if name in sections else None


def _risk_factor_count(sections: dict[str, list[dict]]) -> int | None:
    """Risk factors in Item 1A: its emphasized (bold or italic) paragraphs that are sentences.
    Category headings like "Macroeconomic and Industry Risks" have no period, so don't count."""
    if "Item 1A" not in sections:
        return None
    return sum(1 for b in sections["Item 1A"] if b.get("emphasized") and b["text"].rstrip().endswith("."))


if __name__ == "__main__":
    features = write_features(EdgarDownloader(EdgarClient()))
    print(f"Wrote {len(features)} rows to {FEATURES}", file=sys.stderr)
