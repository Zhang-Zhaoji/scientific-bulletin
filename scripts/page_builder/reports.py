from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .articles import render_markdown_with_article_cards
from .core import DEFAULT_TITLE, report_date_from_name, slugify
from .markdown_render import require_markdown
from .page import render_page
from .sources import report_article_url_maps_by_order
from .styles import CSS


@dataclass(frozen=True)
class ReportLink:
    title: str
    page_name: str
    source_name: str
    cover_src: str | None


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


def discover_reports(input_dir: Path) -> list[Path]:
    return sorted(
        (path for path in input_dir.glob("report_*.md") if "_wechat" not in path.stem),
        key=lambda path: (report_date_from_name(path), path.name),
    )


def write_site_assets(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    icon_dir = assets_dir / "icons"
    icon_dir.mkdir(exist_ok=True)
    folder_icon = Path("Imgs") / "web_asset" / "folder.svg"
    if folder_icon.exists():
        shutil.copy2(folder_icon, icon_dir / folder_icon.name)


def regular_report_body(report_path: Path, markdown_text: str, issue_idx: int, output_dir: Path) -> tuple[str, str]:
    title = generated_report_title(report_path, markdown_text, issue_idx)
    report_body = trim_report_body(markdown_text)
    media_html = render_report_media(report_path, output_dir)
    report_body = insert_report_media_after_overview(report_body, media_html)
    return title, report_body


def special_issue_body(input_dir: Path, output_dir: Path, report_path: Path, markdown_text: str, issue_idx: int) -> tuple[str, str]:
    copy_special_issue_assets(input_dir, output_dir, issue_idx)
    heading = first_markdown_heading(markdown_text)
    title = "神经科学快讯·special issue"
    if heading:
        title = f"{title}｜{heading}"
    report_body = strip_first_markdown_heading(markdown_text)
    report_body = rewrite_special_issue_asset_paths(report_body, issue_idx)
    return title, report_body


def render_report_page(
    input_dir: Path,
    output_dir: Path,
    report_path: Path,
    issue_numbers: dict[Path, int],
    special_issue_numbers: dict[Path, int],
    article_url_maps: dict[Path, dict[str, str]],
) -> ReportLink:
    markdown_text = report_path.read_text(encoding="utf-8")
    is_special = is_special_issue(report_path)

    if is_special:
        title, report_body = special_issue_body(
            input_dir,
            output_dir,
            report_path,
            markdown_text,
            special_issue_numbers[report_path],
        )
        article_urls = {}
    else:
        title, report_body = regular_report_body(report_path, markdown_text, issue_numbers[report_path], output_dir)
        article_urls = article_url_maps.get(report_path, {})

    cover_src = report_cover_src(report_path, output_dir)
    body = render_markdown_with_article_cards(f"# {title}\n\n{report_body}", article_urls)
    page_name = slugify(report_path)
    (output_dir / page_name).write_text(render_page(title, body, cover_src=cover_src), encoding="utf-8")
    return ReportLink(title, page_name, report_path.name, cover_src)


def render_index_page(input_dir: Path, output_dir: Path, report_links: list[ReportLink]) -> None:
    items = "\n".join(
        render_report_link(report_link.title, report_link.page_name, report_link.source_name, report_link.cover_src)
        for report_link in report_links
    )
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


def build_site(input_dir: Path, output_dir: Path) -> None:
    require_markdown()

    reports = discover_reports(input_dir)
    regular_reports = [path for path in reports if not is_special_issue(path)]
    special_reports = [path for path in reports if is_special_issue(path)]
    issue_numbers = {path: idx for idx, path in enumerate(regular_reports, 1)}
    special_issue_numbers = {path: idx for idx, path in enumerate(special_reports, 1)}
    article_url_maps = report_article_url_maps_by_order(input_dir, regular_reports)

    write_site_assets(output_dir)
    report_links = [
        render_report_page(input_dir, output_dir, report_path, issue_numbers, special_issue_numbers, article_url_maps)
        for report_path in reversed(reports)
    ]
    render_index_page(input_dir, output_dir, report_links)
