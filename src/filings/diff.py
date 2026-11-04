"""Compare the same Section across two Filings: similarity score plus added/removed paragraphs.

Similarity is the cosine similarity of the two Sections' word counts, the
measure Cohen, Malloy & Nguyen (2020, "Lazy Prices") use for year-over-year
change. Paragraphs are compared after normalizing whitespace and case; an
added paragraph whose words overlap a removed one by at least 80% is a
rewording, reported as a (old, new) pair in ``changed`` rather than as one
removed and one added.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from src.filings.parse import parse_sections

_WORD = re.compile(r"\w+")
REWORDING = 0.8


def section_paragraphs(folder: Path, primary_document: str, form: str, section: str) -> list[str] | None:
    """The paragraphs (text blocks and tables) of one Section of a saved Filing,
    or None if the Filing has no such Section."""
    for s in parse_sections((folder / primary_document).read_bytes(), form):
        if s["section"] == section:
            return [b["text"] for b in s["blocks"]]
    return None


def diff_paragraphs(a: list[str], b: list[str]) -> dict:
    """Similarity of ``b`` to ``a``; paragraphs added in ``b``, removed from ``a``,
    and reworded (``changed``, as ``(old, new)`` pairs)."""
    counts_a = Counter(_WORD.findall(" ".join(a).lower()))
    counts_b = Counter(_WORD.findall(" ".join(b).lower()))
    dot = sum(n * counts_b[w] for w, n in counts_a.items())
    norm = math.sqrt(sum(n * n for n in counts_a.values()) * sum(n * n for n in counts_b.values()))

    def key(p: str) -> str:
        return " ".join(p.lower().split())

    keys_a, keys_b = {key(p) for p in a}, {key(p) for p in b}
    added = [p for p in b if key(p) not in keys_a]
    removed = [p for p in a if key(p) not in keys_b]

    changed = []
    for new in list(added):
        scored = [(SequenceMatcher(None, old.split(), new.split()).ratio(), old) for old in removed]
        score, old = max(scored, default=(0.0, None))
        if score >= REWORDING:
            changed.append((old, new))
            added.remove(new)
            removed.remove(old)
    return {
        "similarity": dot / norm if norm else 0.0,
        "added": added,
        "removed": removed,
        "changed": changed,
    }
