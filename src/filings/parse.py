"""Split filing HTML into Sections and convert tables to markdown.

A 10-K is split into the Sections ``Item 1``, ``1A``, ``7``, ``7A``, ``8`` and
``9A``. Headings are found only outside data tables, so the table of contents
(a multi-column table) never starts a Section; if an Item heading still occurs
more than once, the occurrence with the most content wins.
"""

from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

TEN_K_SECTIONS = ("Item 1", "Item 1A", "Item 7", "Item 7A", "Item 8", "Item 9A")

_BLOCK_TAGS = ["p", "div", "table", "li", "h1", "h2", "h3", "h4", "h5", "h6"]
_HEADING = re.compile(r"^\s*(?:item\s+(\d{1,2}[a-c]?)\s*[.:\s]|part\s+[iv]+\b)", re.IGNORECASE)
_MAX_HEADING_CHARS = 200

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def parse_10k(html: bytes) -> list[dict]:
    """Sections of a 10-K in document order.

    Each Section is ``{"section": "Item 1A", "blocks": [{"text", "is_table"}]}``;
    a table block is markdown with its caption on the first line.
    """
    segments: list[tuple[str | None, list[dict]]] = []
    for block in _blocks(BeautifulSoup(html, "lxml")):
        match = None if block["is_table"] else _HEADING.match(block["text"])
        if match and len(block["text"]) <= _MAX_HEADING_CHARS:
            item = f"Item {match.group(1).upper()}" if match.group(1) else None
            segments.append((item, []))
        elif segments:
            segments[-1][1].append(block)

    best: dict[str, list[dict]] = {}
    for item, blocks in segments:
        if item in TEN_K_SECTIONS and _size(blocks) > _size(best.get(item, [])):
            best[item] = blocks
    return [{"section": s, "blocks": best[s]} for s in TEN_K_SECTIONS if s in best]


def _blocks(soup: BeautifulSoup) -> list[dict]:
    """Leaf text blocks and data tables in document order.

    Layout tables (at most one non-empty cell per row) are read as text. The
    short text block right before a data table becomes its caption.
    """
    blocks: list[dict] = []
    for el in soup.find_all(_BLOCK_TAGS):
        if el.find_parent("table"):
            continue
        if el.name == "table":
            rows = _rows(el)
            if all(len(r) <= 1 for r in rows):
                blocks += [{"text": r[0], "is_table": False} for r in rows if r]
                continue
            caption = ""
            if blocks and not blocks[-1]["is_table"] and len(blocks[-1]["text"]) <= _MAX_HEADING_CHARS \
                    and not _HEADING.match(blocks[-1]["text"]):
                caption = blocks.pop()["text"] + "\n\n"
            blocks.append({"text": caption + _markdown(rows), "is_table": True})
        elif not el.find(_BLOCK_TAGS):
            text = el.get_text(" ", strip=True)
            if text:
                blocks.append({"text": text, "is_table": False})
    return blocks


def _rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        row: list[str] = []
        for cell in tr.find_all(["td", "th"]):
            text = cell.get_text(" ", strip=True)
            if text in ("%", ")", ")%") and row:  # EDGAR puts units in their own cells
                row[-1] += text
            elif row and row[-1] in ("$", "("):
                row[-1] += text
            elif text:
                row.append(text)
        rows.append(row)
    return rows


def _markdown(rows: list[list[str]]) -> str:
    rows = [r for r in rows if r]
    width = max(len(r) for r in rows)
    rows[0] = [""] * (width - len(rows[0])) + rows[0]  # header's empty corner cell
    lines =["| " + " | ".join(r) + " |" for r in rows]
    lines.insert(1, "|" + " --- |" * width)
    return "\n".join(lines)


def _size(blocks: list[dict]) -> int:
    return sum(len(b["text"]) for b in blocks)
