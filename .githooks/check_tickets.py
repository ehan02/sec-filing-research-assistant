"""Fail when a ticket's Status line disagrees with its checkboxes.

Every box ticked means ``**Status:** done``; ``done`` means every box ticked.
"""

import re
import sys
from pathlib import Path

STATUS = re.compile(r"^\*\*Status:\*\* *(\S+)", re.MULTILINE)

problems = []
for path in sorted(Path(".scratch").glob("*/issues/*.md")):
    text = path.read_text(encoding="utf-8")
    boxes = re.findall(r"^- \[(.)\]", text, re.MULTILINE)
    status = STATUS.search(text)
    if not boxes or not status:
        continue
    finished = all(b == "x" for b in boxes)
    if finished != (status.group(1) == "done"):
        want = "done" if finished else "not done (boxes are unticked)"
        problems.append(f"{path}: Status is {status.group(1)}, should be {want}")

if problems:
    print("Ticket Status lines out of date:", *problems, sep="\n  ")
    sys.exit(1)
