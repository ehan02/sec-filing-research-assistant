"""Split filing HTML into Sections and convert tables to markdown.

Sections are form-aware:

- an Original 10-K keeps ``Item 1``, ``1A``, ``7``, ``7A``, ``8`` and ``9A``;
- a 10-Q keeps every Item, qualified by its Part (``Part II Item 1A``);
- an Amendment keeps every Item it contains, since it only holds what it amends;
- an 8-K exhibit is one Section named after it (``Ex-99.1``).

Headings are found only outside data tables, so the table of contents (a
multi-column table) never starts a Section; if an Item heading still occurs
more than once, the occurrence with the most content wins.
"""

from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

TEN_K_SECTIONS = ("Item 1", "Item 1A", "Item 7", "Item 7A", "Item 8", "Item 9A")

_BLOCK_TAGS = ["p", "div", "table", "li", "h1", "h2", "h3", "h4", "h5", "h6"]
_HEADING = re.compile(r"^\s*(?:item\s+(\d{1,2}[a-c]?)\s*[.:\s]|part\s+([iv]+)\b)", re.IGNORECASE)
_EXHIBIT = re.compile(r"ex-?99[._-]?(\d*)", re.IGNORECASE)
_MAX_HEADING_CHARS = 200

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def parse_sections(html: bytes, form: str) -> list[dict]:
    """Sections of a 10-K or 10-Q (or their Amendments) in document order.

    Each Section is ``{"section": "Item 1A", "blocks": [{"text", "is_table"}]}``;
    a table block is markdown with its caption on the first line.
    """
    with_part = form.upper().startswith("10-Q")
    segments: list[tuple[str | None, list[dict]]] = []
    part = None
    for block in _blocks(BeautifulSoup(html, "lxml")):
        match = None if block["is_table"] else _HEADING.match(block["text"])
        if match and len(block["text"]) <= _MAX_HEADING_CHARS:
            item, roman = match.groups()
            if roman:
                part = roman.upper()
                segments.append((None, []))
            else:
                name = f"Item {item.upper()}"
                segments.append((f"Part {part} {name}" if with_part else name, []))
        elif segments:
            segments[-1][1].append(block)

    keep_all = with_part or form.upper().endswith("/A")
    best: dict[str, tuple[int, list[dict]]] = {}
    for position, (section, blocks) in enumerate(segments):
        if section and (keep_all or section in TEN_K_SECTIONS) and blocks \
                and _size(blocks) > _size(best.get(section, (0, []))[1]):
            best[section] = (position, blocks)
    return [{"section": s, "blocks": blocks}
            for s, (_, blocks) in sorted(best.items(), key=lambda kv: kv[1][0])]


def parse_exhibit(html: bytes, filename: str) -> dict:
    """An 8-K exhibit as one Section named after it, e.g. ``Ex-99.1``."""
    number = _EXHIBIT.search(filename).group(1)
    name = f"Ex-99.{number}" if number else "Ex-99"
    return {"section": name, "blocks": _blocks(BeautifulSoup(html, "lxml"))}


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
