"""
Build a small static website from generated Markdown reports.

Usage:
    python scripts/build_pages.py
    python scripts/build_pages.py --input-dir LLM_Results --output-dir docs
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

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
  display: block;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--accent);
  text-decoration: none;
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
@media (max-width: 680px) {
  .site-head { align-items: flex-start; flex-direction: column; }
  .nav a { margin-left: 0; margin-right: 14px; }
  .paper { padding: 18px; }
  table { display: block; overflow-x: auto; white-space: nowrap; }
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

    quote_idx = next(
        (idx for idx, line in enumerate(lines) if line.lstrip().startswith(">")),
        None
    )
    if quote_idx is not None:
        return "\n".join(lines[quote_idx:]).strip()

    overview_idx = next(
        (idx for idx, line in enumerate(lines) if "📊 本周概览" in line),
        None
    )
    if overview_idx is not None:
        return "\n".join(lines[overview_idx:]).strip()

    return markdown_text.strip()


def render_page(title: str, body: str, root_prefix: str = "") -> str:
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
        <a href="{root_prefix}index.html">Reports</a>
        <a href="https://github.com/">GitHub</a>
      </nav>
    </div>
  </header>
  <main class="wrap">
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


def render_markdown_with_article_cards(markdown_text: str) -> str:
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
            parts.append(f'<section class="article-card">\n{markdown_to_html(article_markdown)}\n</section>')
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
    issue_numbers = {path: idx for idx, path in enumerate(reports, 1)}
    display_reports = list(reversed(reports))
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    report_links = []
    for report_path in display_reports:
        markdown_text = report_path.read_text(encoding="utf-8")
        title = generated_report_title(report_path, markdown_text, issue_numbers[report_path])
        report_body = trim_report_body(markdown_text)
        body = render_markdown_with_article_cards(f"# {title}\n\n{report_body}")
        page_name = slugify(report_path)
        (output_dir / page_name).write_text(render_page(title, body), encoding="utf-8")
        report_links.append((title, page_name, report_path.name))

    items = "\n".join(
        f'<li><a href="{html.escape(page_name)}"><strong>{html.escape(title)}</strong>'
        f'<br><span class="meta">{html.escape(source_name)}</span></a></li>'
        for title, page_name, source_name in report_links
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GitHub Pages static HTML from Markdown reports.")
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
