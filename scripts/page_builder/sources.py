from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from .core import json_date_from_name, report_date_from_name


def parse_iso_date(date_text: str) -> datetime | None:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return None


def normalize_title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title or "").strip().casefold()


def source_base_url(raw_data: dict) -> str:
    source = str(raw_data.get("source") or raw_data.get("original_source") or raw_data.get("journal") or "").lower()
    if "nature" in source:
        return "https://www.nature.com/"
    if "science" in source:
        return "https://www.science.org/"
    if "cell" in source or "neuron" in source or "current biology" in source:
        return "https://www.cell.com/"
    if "pnas" in source:
        return "https://www.pnas.org/"
    return "https://www.google.com/"


def google_search_url(title: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(title)}"


def article_link_from_raw_data(raw_data: dict, title: str) -> str:
    url = raw_data.get("url")
    doi = raw_data.get("doi")

    if url:
        url = str(url).strip()
        if re.match(r"^https?://", url):
            return url
        if url.startswith("/") or not re.match(r"^[a-z]+:", url, flags=re.IGNORECASE):
            return urljoin(source_base_url(raw_data), url)

    if doi:
        return f"https://doi.org/{doi}"

    return google_search_url(title)


def build_article_url_map(json_path: Path) -> dict[str, str]:
    """
    Load one LLM result JSON and return title -> source URL.
    """
    with json_path.open("r", encoding="utf-8") as f:
        json_list = json.load(f)

    url_map = {}
    for item in json_list:
        raw_data = item.get("paper", {}).get("raw_data", {})
        title_candidates = [
            raw_data.get("title"),
            item.get("paper", {}).get("title"),
        ]
        for title in title_candidates:
            if title:
                url = article_link_from_raw_data(raw_data, title)
                url_map[normalize_title_key(title)] = url
    return url_map


def exact_date_article_url_map(input_dir: Path, report_path: Path) -> dict[str, str]:
    """
    Find the LLM result JSON for a report date and build a title -> URL map.
    If there are multiple JSON files for the same date, the lexicographically
    latest one is used.
    """
    report_date = report_date_from_name(report_path)
    candidates = sorted(
        (path for path in input_dir.glob("LLM_results_*.json") if json_date_from_name(path) == report_date),
        key=lambda path: path.name,
    )
    if not candidates:
        return {}
    return build_article_url_map(candidates[-1])


def report_article_url_maps_by_order(input_dir: Path, regular_reports: list[Path]) -> dict[Path, dict[str, str]]:
    """
    Pair regular reports with LLM result JSON files.
    The report and JSON dates may differ slightly, so each report prefers the
    latest unused JSON whose date is not later than the report date.
    """
    json_files = sorted(
        input_dir.glob("LLM_results_*.json"),
        key=lambda path: (json_date_from_name(path), path.name),
    )
    json_entries = [
        (path, parse_iso_date(json_date_from_name(path)))
        for path in json_files
    ]

    article_url_maps = {}
    used_json_paths = set()
    for report_path in regular_reports:
        report_dt = parse_iso_date(report_date_from_name(report_path))
        selected_json = None

        if report_dt is not None:
            eligible = [
                (json_path, json_dt)
                for json_path, json_dt in json_entries
                if json_path not in used_json_paths and json_dt is not None and json_dt <= report_dt
            ]
            if eligible:
                selected_json = max(eligible, key=lambda item: (item[1], item[0].name))[0]

        if selected_json is None:
            selected_json = next(
                (json_path for json_path, _ in json_entries if json_path not in used_json_paths),
                None
            )

        if selected_json is not None:
            used_json_paths.add(selected_json)
            article_url_maps[report_path] = build_article_url_map(selected_json)

    for report_path in regular_reports:
        if report_path not in article_url_maps:
            article_url_maps[report_path] = exact_date_article_url_map(input_dir, report_path)
    return article_url_maps
