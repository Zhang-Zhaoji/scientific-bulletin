from __future__ import annotations

import ast
import hashlib
import html
import re

from .markdown_render import markdown_to_html
from .sources import google_search_url, normalize_title_key


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


CARD_METADATA_FIELDS = {"推荐等级", "评分", "期刊", "日期", "发表日期", "研究领域"}
BOLD_FIELD_RE = re.compile(r"\*\*([^*]+)\*\*:\s*")


def split_bold_fields(line: str) -> list[tuple[str, str]]:
    stripped = line.strip()
    matches = list(BOLD_FIELD_RE.finditer(stripped))
    if not matches or matches[0].start() != 0:
        return []

    fields = []
    for index, match in enumerate(matches):
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(stripped)
        value = stripped[value_start:value_end].strip()
        value = re.sub(r"\s*\|\s*$", "", value).strip()
        fields.append((match.group(1).strip(), value))
    return fields


def parse_bold_field(line: str) -> tuple[str, str] | None:
    fields = split_bold_fields(line)
    if not fields:
        return None
    return fields[0]


def clean_inline_markdown(value: str) -> str:
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", value)
    return value.strip()


def split_journal_date(value: str) -> tuple[str, str | None]:
    parts = [clean_inline_markdown(part) for part in value.split("|")]
    journal = parts[0].strip()
    date = None
    for part in parts[1:]:
        if "日期" in part:
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
        parsed_fields = split_bold_fields(line)
        if parsed_fields:
            kept_fields = []
            for field_name, field_value in parsed_fields:
                if field_name in CARD_METADATA_FIELDS:
                    fields[field_name] = clean_inline_markdown(field_value)
                else:
                    kept_fields.append(f"**{field_name}**: {field_value}".strip())
            if kept_fields:
                kept_lines.append(" | ".join(kept_fields))
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
    if fields.get("日期") or fields.get("发表日期"):
        metadata["date"] = fields.get("日期") or fields.get("发表日期")
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


def article_title_and_url(article_markdown: str) -> tuple[str, str]:
    first_line = article_markdown.splitlines()[0].strip() if article_markdown.splitlines() else ""
    title_match = re.match(r"^###\s+(.+?)\s*$", first_line)
    if not title_match:
        return "Untitled", ""
    title = title_match.group(1).strip()
    link_match = re.match(r"\[(.+?)\]\(<(.+?)>\)", title)
    if link_match:
        return link_match.group(1).strip(), link_match.group(2).strip()
    link_match = re.match(r"\[(.+?)\]\((.+?)\)", title)
    if link_match:
        return link_match.group(1).strip(), link_match.group(2).strip()
    return title, ""


def article_card_attrs(article_markdown: str) -> str:
    title, url = article_title_and_url(article_markdown)
    favorite_id = hashlib.sha1(f"{title}\n{url}".encode("utf-8")).hexdigest()[:16]
    attrs = {
        "data-favorite-id": favorite_id,
        "data-favorite-title": title,
        "data-favorite-url": url,
        "data-favorite-markdown": article_markdown,
    }
    return " ".join(f'{key}="{html.escape(value, quote=True)}"' for key, value in attrs.items())


def favorite_button_html() -> str:
    return (
        '<button class="favorite-toggle" type="button" data-favorite-toggle aria-pressed="false">'
        '<img src="assets/icons/folder.svg" alt="">'
        "<span>收藏</span>"
        "</button>"
    )


def add_article_card_chrome(article_html: str, metadata: dict[str, str]) -> str:
    badge = metadata.get("badge")
    favorite_button = favorite_button_html()
    if badge:
        article_html = re.sub(
            r"(<h3[^>]*>.*?</h3>)",
            r'<div class="article-card-head">\1'
            + f'<span class="article-card-actions"><span class="article-badge">{html.escape(badge)}</span>{favorite_button}</span></div>',
            article_html,
            count=1,
            flags=re.DOTALL,
        )
    else:
        article_html = re.sub(
            r"(<h3[^>]*>.*?</h3>)",
            r'<div class="article-card-head">\1'
            + f'<span class="article-card-actions">{favorite_button}</span></div>',
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


def render_article_card(article_markdown: str, article_urls: dict[str, str]) -> str:
    article_markdown = link_article_heading(article_markdown, article_urls)
    article_attrs = article_card_attrs(article_markdown)
    article_markdown, metadata = article_card_metadata(article_markdown)
    article_html = add_article_card_chrome(markdown_to_html(article_markdown), metadata)
    return f'<section class="article-card" {article_attrs}>\n{article_html}\n</section>'


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
            parts.append(render_article_card(article_markdown, article_urls))
            continue

        plain_buffer.append(lines[index])
        index += 1

    flush_plain()
    return "\n".join(part for part in parts if part)
