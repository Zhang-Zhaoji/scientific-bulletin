"""
Build a small static website from generated Markdown reports.

Usage:
    python scripts/build_pages.py
    python scripts/build_pages.py --input-dir LLM_Results --output-dir docs
"""

from __future__ import annotations

import argparse
import ast
import html
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
import json
from urllib.parse import quote_plus, urljoin

try:
    import markdown
except ImportError:
    markdown = None


DEFAULT_TITLE = "Neuroscience Bulletin"


CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fb;
  --paper: #ffffff;
  --ink: #17202a;
  --muted: #5e6b78;
  --line: #dfe4ea;
  --accent: #1769aa;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif;
  line-height: 1.65;
  color: var(--ink);
  background: var(--bg);
}
header {
  border-bottom: 1px solid var(--line);
  background: var(--paper);
}
.wrap {
  width: min(1080px, calc(100% - 32px));
  margin: 0 auto;
}
.site-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0;
}
.brand {
  font-size: 18px;
  font-weight: 700;
  color: var(--ink);
  text-decoration: none;
}
.nav a {
  color: var(--muted);
  text-decoration: none;
  margin-left: 16px;
}
main {
  padding: 28px 0 48px;
}
.cover-hero {
  width: min(60%, 980px);
  margin: 0 auto;
  overflow: hidden;
}
.cover-hero img {
  display: block;
  width: 100%;
  height: auto;
}
.cover-hero + main {
  margin-top: -96px;
  position: relative;
}
.paper {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 28px;
}
.article-card {
  margin: 22px 0;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfdff;
}
.article-card h3 {
  margin-top: 0;
  color: var(--accent);
}
.article-card h3 a {
  color: inherit;
  text-decoration: none;
}
.article-card h3 a:hover {
  text-decoration: underline;
}
.article-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.article-card-head h3 {
  margin-bottom: 10px;
}
.article-badge {
  flex: 0 0 auto;
  padding: 5px 10px;
  border-radius: 999px;
  background: #e9f3ff;
  color: #0f5d9e;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}
.article-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 4px 0 16px;
}
.article-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 4px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #ffffff;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.3;
}
.article-card p:last-child,
.article-card ul:last-child {
  margin-bottom: 0;
}
.report-list {
  display: grid;
  gap: 12px;
  padding: 0;
  list-style: none;
}
.report-list a {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--accent);
  text-decoration: none;
}
.report-thumb {
  width: 132px;
  aspect-ratio: 16 / 10;
  object-fit: cover;
  border-radius: 6px;
}
h1, h2, h3 {
  line-height: 1.25;
}
h1 { font-size: 30px; }
h2 {
  margin-top: 34px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0 22px;
  font-size: 15px;
}
th, td {
  border: 1px solid var(--line);
  padding: 8px 10px;
  vertical-align: top;
}
th { background: #eef3f8; }
code, pre {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}
pre {
  overflow-x: auto;
  padding: 14px;
  border-radius: 8px;
  background: #101828;
  color: #f8fafc;
}
blockquote {
  margin-left: 0;
  padding-left: 16px;
  border-left: 4px solid var(--line);
  color: var(--muted);
}
img {
  max-width: 100%;
  height: auto;
}
.meta {
  color: var(--muted);
}
.report-media {
  display: grid;
  gap: 20px;
  margin: 28px 0;
}
.chart-grid {
  display: grid;
  gap: 18px;
}
.chart-frame {
  width: 100%;
  aspect-ratio: 16 / 9;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
}
@media (max-width: 680px) {
  .site-head { align-items: flex-start; flex-direction: column; }
  .nav a { margin-left: 0; margin-right: 14px; }
  .cover-hero { width: 100%; }
  .cover-hero + main { margin-top: -36px; }
  .paper { padding: 18px; }
  .article-card-head { flex-direction: column; gap: 6px; }
  .report-list a { grid-template-columns: 1fr; }
  .report-thumb { width: 100%; }
  table { display: block; overflow-x: auto; white-space: nowrap; }
}
.video-embed {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  margin: 24px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: #000;
}

.video-embed iframe {
  width: 100%;
  height: 100%;
  display: block;
}
"""


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


def is_special_issue(path: Path) -> bool:
    return path.stem.endswith("_specialissue")


def first_markdown_heading(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def report_asset_dates(report_path: Path) -> list[datetime]:
    report_date = datetime.strptime(report_date_from_name(report_path), "%Y-%m-%d")
    if is_special_issue(report_path):
        return [report_date, report_date - timedelta(days=1)]
    return [report_date - timedelta(days=1), report_date]


def copy_asset(source_path: Path, output_dir: Path, asset_subdir: str) -> str:
    asset_dir = output_dir / "assets" / asset_subdir
    asset_dir.mkdir(parents=True, exist_ok=True)
    target_path = asset_dir / source_path.name
    shutil.copy2(source_path, target_path)
    return f"assets/{asset_subdir}/{html.escape(target_path.name)}"


def localize_chart_html(chart_path: Path) -> None:
    text = chart_path.read_text(encoding="utf-8")
    text = text.replace(
        "https://assets.pyecharts.org/assets/v6/echarts.min.js",
        "../vendor/echarts.min.js",
    )
    text = text.replace(
        "https://assets.pyecharts.org/assets/v6/maps/world.js",
        "../vendor/world.js",
    )
    chart_path.write_text(text, encoding="utf-8")


def first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def report_cover_src(report_path: Path, output_dir: Path) -> str | None:
    candidate_dates = report_asset_dates(report_path)
    compact_dates = [date.strftime("%Y%m%d") for date in candidate_dates]
    cover_path = first_existing([Path("Imgs") / f"{date}.png" for date in compact_dates])
    if not cover_path:
        return None
    return copy_asset(cover_path, output_dir, "covers")


def render_report_media(report_path: Path, output_dir: Path) -> str:
    candidate_dates = report_asset_dates(report_path)
    iso_dates = [date.strftime("%Y-%m-%d") for date in candidate_dates]

    heatmap_path = first_existing([
        Path("Imgs") / "visulize_img" / "globalHeatmap" / f"{date}_heatmap.html"
        for date in iso_dates
    ])
    pie_path = first_existing([
        Path("Imgs") / "visulize_img" / "countryPie" / f"{date}_pie.html"
        for date in iso_dates
    ])

    media_parts = []
    chart_frames = []
    if heatmap_path:
        heatmap_src = copy_asset(heatmap_path, output_dir, "charts")
        localize_chart_html(output_dir / heatmap_src)
        chart_frames.append(f'<iframe class="chart-frame" title="Country heatmap" src="{heatmap_src}" loading="lazy"></iframe>')
    if pie_path:
        pie_src = copy_asset(pie_path, output_dir, "charts")
        localize_chart_html(output_dir / pie_src)
        chart_frames.append(f'<iframe class="chart-frame" title="Country distribution pie chart" src="{pie_src}" loading="lazy"></iframe>')
    if chart_frames:
        media_parts.append(f'<div class="chart-grid">\n{"".join(chart_frames)}\n</div>')

    if not media_parts:
        return ""
    return '<section class="report-media">\n<h2>🌏 环球视野</h2>\n' + "\n".join(media_parts) + "\n</section>\n"


def insert_report_media_after_overview(report_body: str, media_html: str) -> str:
    if not media_html:
        return report_body
    lines = report_body.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() in {"---", "***", "___"}:
            return "\n".join(lines[:idx + 1]) + "\n\n" + media_html + "\n" + "\n".join(lines[idx + 1:])
    return media_html + "\n" + report_body


def render_report_link(title: str, page_name: str, source_name: str, cover_src: str | None) -> str:
    cover_html = ""
    if cover_src:
        cover_html = f'<img class="report-thumb" src="{html.escape(cover_src)}" alt="">'
    return (
        f'<li><a href="{html.escape(page_name)}"><span><strong>{html.escape(title)}</strong>'
        f'<br><span class="meta">{html.escape(source_name)}</span></span>'
        f'{cover_html}</a></li>'
    )


def copy_special_issue_assets(input_dir: Path, output_dir: Path, special_issue_idx: int) -> None:
    source_dir = input_dir / "specialissue" / str(special_issue_idx)
    if not source_dir.exists():
        return
    target_dir = output_dir / "assets" / "specialissue" / str(special_issue_idx)
    target_dir.mkdir(parents=True, exist_ok=True)
    for source_path in source_dir.iterdir():
        if source_path.is_file():
            shutil.copy2(source_path, target_dir / source_path.name)


def rewrite_special_issue_asset_paths(markdown_text: str, special_issue_idx: int) -> str:
    source_prefix = rf"specialissue[\\/]{special_issue_idx}[\\/]"
    target_prefix = f"assets/specialissue/{special_issue_idx}/"
    return re.sub(rf"(?<!assets[\\/]){source_prefix}", target_prefix, markdown_text)


def strip_first_markdown_heading(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("# "):
            return "\n".join(lines[:idx] + lines[idx + 1:]).strip()
    return markdown_text.strip()


def pre_overview_text(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    overview_idx = next(
        (idx for idx, line in enumerate(lines) if "📊 本周概览" in line),
        None
    )
    if overview_idx is None:
        return markdown_text
    return "\n".join(lines[:overview_idx])


def first_bracket_title(markdown_text: str) -> str:
    intro_text = pre_overview_text(markdown_text)
    match = re.search(r"《([^》]+)》", intro_text)
    if not match:
        match = re.search(r"\*\*((?:(?!\d[\d\.]*\+?\s*分)[^*\n])+?)\*\*", intro_text)
        
    return match.group(1).strip() if match else ""


def generated_report_title(path: Path, markdown_text: str, issue_idx: int) -> str:
    bracket_title = first_bracket_title(markdown_text)
    subtitle = f"{bracket_title} " if bracket_title else ""
    return f"神经科学快讯·第{issue_idx:03d}期 {subtitle}({report_date_from_name(path)})"


def trim_report_body(markdown_text: str) -> str:
    lines = markdown_text.splitlines()

    overview_idx = next(
        (idx for idx, line in enumerate(lines) if "📊 本周概览" in line),
        None
    )
    if overview_idx is not None:
        return "\n".join(lines[overview_idx:]).strip()

    quote_idx = next(
        (idx for idx, line in enumerate(lines) if line.lstrip().startswith(">")),
        None
    )
    if quote_idx is not None:
        return "\n".join(lines[quote_idx:]).strip()

    return markdown_text.strip()


def render_page(title: str, body: str, root_prefix: str = "", cover_src: str | None = None) -> str:
    cover_html = ""
    if cover_src:
        cover_html = f'  <section class="cover-hero"><img src="{cover_src}" alt=""></section>\n'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} | {DEFAULT_TITLE}</title>
  <link rel="stylesheet" href="{root_prefix}assets/style.css">
</head>
<body>
  <header>
    <div class="wrap site-head">
      <a class="brand" href="{root_prefix}index.html">{DEFAULT_TITLE}</a>
      <nav class="nav">
        <a href="https://github.com/Zhang-Zhaoji/scientific-bulletin/issues">Reports</a>
        <a href="https://github.com/Zhang-Zhaoji/scientific-bulletin/">GitHub</a>
      </nav>
    </div>
  </header>
{cover_html}  <main class="wrap">
    <article class="paper">
{body}
    </article>
  </main>
</body>
</html>
"""


def basic_markdown_to_html(markdown_text: str) -> str:
    """Small fallback renderer for local previews when Python-Markdown is not installed."""
    blocks = []
    in_list = False
    in_code = False
    code_lines = []

    def close_list():
        nonlocal in_list
        if in_list:
            blocks.append("</ul>")
            in_list = False

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_list()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            close_list()
            continue
        if stripped.startswith("#"):
            close_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            text = stripped[level:].strip()
            blocks.append(f"<h{level}>{html.escape(text)}</h{level}>")
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{html.escape(stripped[2:].strip())}</li>")
        else:
            close_list()
            blocks.append(f"<p>{html.escape(stripped)}</p>")
    close_list()
    return "\n".join(blocks)


def markdown_to_html(markdown_text: str) -> str:
    if markdown is None:
        return basic_markdown_to_html(markdown_text)
    md = markdown.Markdown(extensions=["extra", "toc", "sane_lists"])
    return md.convert(markdown_text)


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


def link_article_heading(article_markdown: str, article_urls: dict[str, str]) -> str:
    lines = article_markdown.splitlines()
    if not lines:
        return article_markdown

    match = re.match(r"^(###\s+)(.+?)\s*$", lines[0])
    if not match:
        return article_markdown

    prefix, title = match.groups()
    if "](" in title:
        return article_markdown

    url = article_urls.get(normalize_title_key(title)) or google_search_url(title)

    escaped_title = title.replace("[", "\\[").replace("]", "\\]")
    safe_url = url.replace("<", "%3C").replace(">", "%3E")
    lines[0] = f"{prefix}[{escaped_title}](<{safe_url}>)"
    return "\n".join(lines)


def parse_bold_field(line: str) -> tuple[str, str] | None:
    match = re.match(r"^\*\*([^*]+)\*\*:\s*(.+?)\s*$", line.strip())
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def clean_inline_markdown(value: str) -> str:
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", value)
    return value.strip()


def split_journal_date(value: str) -> tuple[str, str | None]:
    parts = [clean_inline_markdown(part) for part in value.split("|")]
    journal = parts[0].strip()
    date = None
    for part in parts[1:]:
        if "发表日期" in part:
            date = part.split(":", 1)[-1].strip()
    return journal, date


def clean_domain_value(value: str) -> str:
    value = clean_inline_markdown(value)
    value = re.sub(r"^None\s*/\s*", "", value).strip()
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            return " · ".join(str(item).strip() for item in parsed if str(item).strip())
    parts = [part.strip() for part in value.split(" / ") if part.strip() and part.strip() != "None"]
    cleaned_parts = []
    for part in parts:
        if part.startswith("[") and part.endswith("]"):
            try:
                parsed = ast.literal_eval(part)
            except (SyntaxError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                cleaned_parts.extend(str(item).strip() for item in parsed if str(item).strip())
                continue
        cleaned_parts.append(part)
    return " · ".join(cleaned_parts)


def article_card_metadata(article_markdown: str) -> tuple[str, dict[str, str]]:
    lines = article_markdown.splitlines()
    fields = {}
    kept_lines = []

    for line in lines:
        parsed = parse_bold_field(line)
        if parsed:
            field_name, field_value = parsed
            fields[field_name] = clean_inline_markdown(field_value)
            if field_name in {"推荐等级", "评分", "期刊", "研究领域"}:
                continue
        kept_lines.append(line)

    metadata = {}
    if fields.get("推荐等级") or fields.get("评分"):
        badge_parts = [part for part in [fields.get("推荐等级"), fields.get("评分")] if part]
        metadata["badge"] = " ".join(badge_parts)
    if fields.get("期刊"):
        journal, date = split_journal_date(fields["期刊"])
        if journal:
            metadata["journal"] = journal
        if date:
            metadata["date"] = date
    if fields.get("研究领域"):
        metadata["domain"] = clean_domain_value(fields["研究领域"])

    return "\n".join(kept_lines).strip(), metadata


def render_article_metadata(metadata: dict[str, str]) -> str:
    chips = []
    if metadata.get("journal"):
        chips.append(f'<span class="article-chip">{html.escape(metadata["journal"])}</span>')
    if metadata.get("date"):
        chips.append(f'<span class="article-chip">{html.escape(metadata["date"])}</span>')
    if metadata.get("domain"):
        chips.append(f'<span class="article-chip">{html.escape(metadata["domain"])}</span>')
    if not chips:
        return ""
    return '<div class="article-meta">' + "".join(chips) + "</div>"


def add_article_card_chrome(article_html: str, metadata: dict[str, str]) -> str:
    badge = metadata.get("badge")
    if badge:
        article_html = re.sub(
            r"(<h3[^>]*>.*?</h3>)",
            r'<div class="article-card-head">\1'
            + f'<span class="article-badge">{html.escape(badge)}</span></div>',
            article_html,
            count=1,
            flags=re.DOTALL,
        )
    meta_html = render_article_metadata(metadata)
    if meta_html:
        if 'class="article-card-head"' in article_html:
            article_html = article_html.replace("</div>", f"</div>\n{meta_html}", 1)
        else:
            article_html = re.sub(r"(</h3>)", r"\1\n" + meta_html, article_html, count=1)
    return article_html


def is_article_heading(lines: list[str], index: int) -> bool:
    line = lines[index].strip()
    if not line.startswith("### "):
        return False

    lookahead = []
    for next_line in lines[index + 1:]:
        stripped = next_line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            break
        if stripped:
            lookahead.append(stripped)
        if len(lookahead) >= 12:
            break

    article_markers = ("**中文标题**", "**作者**", "**期刊**", "**推荐等级**", "**评分**")
    marker_count = sum(any(item.startswith(marker) for marker in article_markers) for item in lookahead)
    return marker_count >= 2


def render_markdown_with_article_cards(markdown_text: str, article_urls: dict[str, str] | None = None) -> str:
    article_urls = article_urls or {}
    lines = markdown_text.splitlines()
    parts = []
    plain_buffer = []
    index = 0

    def flush_plain() -> None:
        nonlocal plain_buffer
        if plain_buffer:
            parts.append(markdown_to_html("\n".join(plain_buffer).strip()))
            plain_buffer = []

    while index < len(lines):
        if is_article_heading(lines, index):
            flush_plain()
            start = index
            index += 1
            while index < len(lines):
                stripped = lines[index].strip()
                if stripped.startswith("## ") or stripped.startswith("### "):
                    break
                index += 1
            article_markdown = "\n".join(lines[start:index]).strip()
            article_markdown = link_article_heading(article_markdown, article_urls)
            article_markdown, metadata = article_card_metadata(article_markdown)
            article_html = add_article_card_chrome(markdown_to_html(article_markdown), metadata)
            parts.append(f'<section class="article-card">\n{article_html}\n</section>')
            continue

        plain_buffer.append(lines[index])
        index += 1

    flush_plain()
    return "\n".join(part for part in parts if part)


def build_site(input_dir: Path, output_dir: Path) -> None:
    if markdown is None:
        raise RuntimeError(
            "The 'markdown' package is required for faithful HTML rendering. "
            "Install it with: python -m pip install markdown"
        )

    reports = sorted(
        (path for path in input_dir.glob("report_*.md") if "_wechat" not in path.stem),
        key=lambda path: (report_date_from_name(path), path.name),
    )
    regular_reports = [path for path in reports if not is_special_issue(path)]
    special_reports = [path for path in reports if is_special_issue(path)]
    issue_numbers = {path: idx for idx, path in enumerate(regular_reports, 1)}
    special_issue_numbers = {path: idx for idx, path in enumerate(special_reports, 1)}
    article_url_maps = report_article_url_maps_by_order(input_dir, regular_reports)
    display_reports = list(reversed(reports))
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    report_links = []
    for report_path in display_reports:
        markdown_text = report_path.read_text(encoding="utf-8")
        if is_special_issue(report_path):
            special_issue_idx = special_issue_numbers[report_path]
            copy_special_issue_assets(input_dir, output_dir, special_issue_idx)
            heading = first_markdown_heading(markdown_text)
            title = f"神经科学快讯·special issue"
            if heading:
                title = f"{title}｜{heading}"
            report_body = strip_first_markdown_heading(markdown_text)
            report_body = rewrite_special_issue_asset_paths(report_body, special_issue_idx)
        else:
            title = generated_report_title(report_path, markdown_text, issue_numbers[report_path])
            report_body = trim_report_body(markdown_text)
        cover_src = report_cover_src(report_path, output_dir)
        if not is_special_issue(report_path):
            media_html = render_report_media(report_path, output_dir)
            report_body = insert_report_media_after_overview(report_body, media_html)
        article_urls = {} if is_special_issue(report_path) else article_url_maps.get(report_path, {})
        body = render_markdown_with_article_cards(f"# {title}\n\n{report_body}", article_urls)
        page_name = slugify(report_path)
        (output_dir / page_name).write_text(render_page(title, body, cover_src=cover_src), encoding="utf-8")
        report_links.append((title, page_name, report_path.name, cover_src))

    items = "\n".join(render_report_link(*report_link) for report_link in report_links)
    if not items:
        items = '<li class="meta">No reports found.</li>'

    index_body = f"""
<h1>{DEFAULT_TITLE}</h1>
<p class="meta">Static archive generated from Markdown reports in <code>{html.escape(str(input_dir))}</code>.</p>
<ul class="report-list">
{items}
</ul>
"""
    (output_dir / "index.html").write_text(render_page(DEFAULT_TITLE, index_body), encoding="utf-8")

def build_dict_on_dict(json_file_name)->dict:
    """
    load json files from LLM_results. return a dict of title -> info_json. currently the info_json is used as a simple {url:'...'}
    """
    return build_article_url_map(Path(json_file_name))

def build_site_with_json(input_dir: Path, output_dir: Path) -> None:
    build_site(input_dir, output_dir)


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


if __name__ == "__main__":
    main()
