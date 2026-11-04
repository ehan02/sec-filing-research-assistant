"""PostToolUse hook: after an Edit/Write to a .py file, sort its imports and drop empty f-prefixes.

Only fixes that are safe mid-edit: a broader --fix would delete an import added
one edit before the code that uses it. Remaining lint errors are left to the
pre-commit hook.
"""

import json
import subprocess
import sys
from pathlib import Path

path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
if path.endswith(".py") and Path(path).is_file():
    subprocess.run([sys.executable, "-m", "ruff", "check", "--fix", "-q", "--select", "I,F541",
                    "--exit-zero", path], check=False)
