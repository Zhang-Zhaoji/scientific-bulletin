from __future__ import annotations

import re
from pathlib import Path


DEFAULT_TITLE = "Neuroscience Bulletin"


def slugify(path: Path) -> str:
    name = path.stem.lower()
    name = re.sub(r"[^a-z0-9_-]+", "-", name)
    return f"{name}.html"


def report_date_from_name(path: Path) -> str:
    match = re.search(r"report_(\d{4})(\d{2})(\d{2})", path.stem)
    if not match:
        return path.stem
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def json_date_from_name(path: Path) -> str:
    match = re.search(r"LLM_results_(\d{4})(\d{2})(\d{2})", path.stem)
    if not match:
        return path.stem
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
