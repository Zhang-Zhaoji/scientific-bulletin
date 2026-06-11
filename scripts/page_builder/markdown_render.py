from __future__ import annotations

import html

try:
    import markdown
except ImportError:
    markdown = None


def require_markdown() -> None:
    if markdown is None:
        raise RuntimeError(
            "The 'markdown' package is required for faithful HTML rendering. "
            "Install it with: python -m pip install markdown"
        )


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
