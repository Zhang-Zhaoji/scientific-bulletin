from __future__ import annotations

import html
import re

from .core import DEFAULT_TITLE
from .favorites import favorites_panel, favorites_script


def strip_html_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def unique_heading_id(text: str, index: int, used_ids: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        slug = f"section-{index}"

    candidate = slug
    suffix = 2
    while candidate in used_ids:
        candidate = f"{slug}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def add_floating_toc(body: str) -> tuple[str, str]:
    headings = []
    used_ids = set()
    heading_index = 0
    section_depth = 0
    in_featured_literature = False

    def heading_with_anchor(level: str, attrs: str, content: str) -> str:
        nonlocal heading_index
        text = strip_html_tags(content)
        if not text:
            return f"<h{level}{attrs}>{content}</h{level}>"

        heading_index += 1
        existing_id = re.search(r'\sid=(["\'])(.*?)\1', attrs)
        anchor_id = existing_id.group(2) if existing_id and existing_id.group(2) not in used_ids else ""
        if anchor_id:
            used_ids.add(anchor_id)
        else:
            anchor_id = unique_heading_id(text, heading_index, used_ids)
        attrs = re.sub(r'\sid=(["\']).*?\1', "", attrs)
        headings.append((anchor_id, text, level))
        return f'<h{level} id="{html.escape(anchor_id, quote=True)}"{attrs}>{content}</h{level}>'

    def replace_token(match: re.Match) -> str:
        nonlocal section_depth, in_featured_literature
        token = match.group(0)
        section_tag = match.group("section")
        if section_tag:
            if section_tag.startswith("</"):
                section_depth = max(0, section_depth - 1)
            elif not section_tag.endswith("/>"):
                section_depth += 1
            return token

        level = match.group("level")
        attrs = match.group("attrs")
        content = match.group("content")
        text = strip_html_tags(content)
        if level == "2":
            in_featured_literature = "精选文献" in text
            return heading_with_anchor(level, attrs, content)

        if level == "3" and in_featured_literature and section_depth == 0:
            return heading_with_anchor(level, attrs, content)
        return token

    body = re.sub(
        r"(?P<section></?section\b[^>]*>)|<h(?P<level>[23])(?P<attrs>[^>]*)>(?P<content>.*?)</h(?P=level)>",
        replace_token,
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not headings:
        return body, ""

    links = "\n".join(
        f'      <a class="toc-level-{level}" href="#{html.escape(anchor_id, quote=True)}" data-target="{html.escape(anchor_id, quote=True)}">{html.escape(text)}</a>'
        for anchor_id, text, level in headings
    )
    toc = f"""
  <aside class="floating-toc" aria-label="目录">
    <div class="floating-toc-title">
      <span>目录</span>
      <span class="reading-progress-percent">0%</span>
    </div>
    <div class="reading-progress" aria-hidden="true"><span class="reading-progress-value"></span></div>
    <nav>
{links}
    </nav>
  </aside>
"""
    return body, toc


def floating_toc_script() -> str:
    return """  <script>
    (function () {
      var toc = document.querySelector(".floating-toc");
      if (!toc) return;
      var progressBar = toc.querySelector(".reading-progress-value");
      var progressText = toc.querySelector(".reading-progress-percent");
      var links = Array.prototype.slice.call(toc.querySelectorAll("a[data-target]"));
      var headings = links
        .map(function (link) { return document.getElementById(link.dataset.target); })
        .filter(Boolean);

      function updateToc() {
        var doc = document.documentElement;
        var maxScroll = Math.max(1, doc.scrollHeight - window.innerHeight);
        var pct = Math.max(0, Math.min(100, (window.scrollY / maxScroll) * 100));
        progressBar.style.width = pct.toFixed(0) + "%";
        progressText.textContent = pct.toFixed(0) + "%";

        var active = headings[0];
        headings.forEach(function (heading) {
          if (heading.getBoundingClientRect().top <= 130) active = heading;
        });
        links.forEach(function (link) {
          link.classList.toggle("active", active && link.dataset.target === active.id);
        });
      }

      updateToc();
      window.addEventListener("scroll", updateToc, { passive: true });
      window.addEventListener("resize", updateToc);
    })();
  </script>
"""


def render_page(title: str, body: str, root_prefix: str = "", cover_src: str | None = None) -> str:
    body, toc_html = add_floating_toc(body)
    toc_script = floating_toc_script() if toc_html else ""
    favorite_html = favorites_panel(root_prefix)
    favorite_script = favorites_script()
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
        <a href="{root_prefix}search.html">搜索</a>
        <a href="https://github.com/Zhang-Zhaoji/scientific-bulletin/issues">Reports</a>
        <a href="https://github.com/Zhang-Zhaoji/scientific-bulletin/">GitHub</a>
      </nav>
    </div>
  </header>
{favorite_html}{toc_html}{cover_html}  <main class="wrap">
    <article class="paper">
{body}
    </article>
  </main>
{toc_script}{favorite_script}</body>
</html>
"""
