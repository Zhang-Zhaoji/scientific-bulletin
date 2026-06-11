from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .reports import build_site


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GitHub Pages static HTML from Markdown reports, and use ref jsons as information source")
    parser.add_argument("--input-dir", default="LLM_Results", help="Directory containing report_*.md files.")
    parser.add_argument("--output-dir", default="docs", help="Output directory for static HTML.")
    args = parser.parse_args()
    try:
        build_site(Path(args.input_dir), Path(args.output_dir))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
