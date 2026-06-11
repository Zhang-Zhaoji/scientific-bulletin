from __future__ import annotations

from pathlib import Path

from page_builder.cli import main
from page_builder.reports import build_site
from page_builder.sources import build_article_url_map


def build_dict_on_dict(json_file_name) -> dict:
    """Load an LLM result JSON and return a title -> URL map."""
    return build_article_url_map(Path(json_file_name))


def build_site_with_json(input_dir: Path, output_dir: Path) -> None:
    build_site(input_dir, output_dir)


if __name__ == "__main__":
    main()
