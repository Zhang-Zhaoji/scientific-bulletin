from __future__ import annotations

import json
from pathlib import Path

from .core import title_to_anchor, json_date_from_name, report_date_from_name, slugify
from .page import render_page
from .sources import article_link_from_raw_data, parse_iso_date


def pair_json_to_reports(input_dir: Path, regular_reports: list[Path]) -> dict[Path, Path]:
    """Map each LLM results JSON to its paired regular report path.

    Mirrors the pairing logic in sources.report_article_url_maps_by_order so the
    search index points each paper at the same report page it appears on.
    """
    json_files = sorted(
        input_dir.glob("LLM_results_*.json"),
        key=lambda path: (json_date_from_name(path), path.name),
    )
    json_entries = [
        (path, parse_iso_date(json_date_from_name(path)))
        for path in json_files
    ]

    json_to_report: dict[Path, Path] = {}
    used_json_paths: set[Path] = set()
    for report_path in regular_reports:
        report_dt = parse_iso_date(report_date_from_name(report_path))
        selected_json: Path | None = None

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
                None,
            )

        if selected_json is not None:
            used_json_paths.add(selected_json)
            json_to_report[selected_json] = report_path

    return json_to_report


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_search_doc(item: dict, report_file: str, idx: int) -> dict:
    """Pull the searchable fields out of one LLM result entry.

    Abstracts are truncated to keep the client-side index small enough for
    MiniSearch to build quickly; full abstracts remain on the report pages.
    """
    paper = item.get("paper") or {}
    raw_data = paper.get("raw_data") or {}

    title = _clean(raw_data.get("title") or paper.get("title"))
    abstract = _clean(raw_data.get("abstract") or paper.get("abstract"))
    if len(abstract) > 160:
        abstract = abstract[:160].rstrip() + "…"
    journal = _clean(raw_data.get("journal") or paper.get("journal") or raw_data.get("source"))
    date = _clean(raw_data.get("date") or paper.get("date"))
    url = article_link_from_raw_data(raw_data, title)
    paper_id = _clean(item.get("paper_id"))
    anchor = title_to_anchor(title)

    return {
        "id": str(idx),  # 用序号确保唯一性，避免重复paper_id导致MiniSearch报错
        "title": title,
        "title_zh": _clean(item.get("title_zh")),
        "abstract": abstract,
        "journal": journal,
        "domain": _clean(item.get("domain")),
        "primary_category": _clean(item.get("primary_category")),
        "recommendation_tier": _clean(item.get("recommendation_tier")),
        "total_score": _to_float(item.get("total_score")),
        "date": date,
        "url": url,
        "report_file": report_file,
        "anchor": anchor,
    }


def _load_json_items(json_path: Path) -> list[dict]:
    try:
        with json_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def build_search_index(input_dir: Path, output_dir: Path, regular_reports: list[Path]) -> list[dict]:
    """Scan all LLM result JSONs and write docs/search-index.js."""
    json_to_report = pair_json_to_reports(input_dir, regular_reports)

    docs: list[dict] = []
    idx = 0

    paired_json = sorted(
        json_to_report.keys(),
        key=lambda path: (json_date_from_name(path), path.name),
    )
    for json_path in paired_json:
        report_file = slugify(json_to_report[json_path])
        for item in _load_json_items(json_path):
            if not isinstance(item, dict):
                continue
            idx += 1
            docs.append(extract_search_doc(item, report_file, idx))

    # Index orphan JSON files (no paired report) so all papers remain searchable.
    all_json = sorted(
        input_dir.glob("LLM_results_*.json"),
        key=lambda path: (json_date_from_name(path), path.name),
    )
    for json_path in all_json:
        if json_path in json_to_report:
            continue
        for item in _load_json_items(json_path):
            if not isinstance(item, dict):
                continue
            idx += 1
            docs.append(extract_search_doc(item, "", idx))

    output_dir.mkdir(parents=True, exist_ok=True)
    # 输出为 JS 文件（JSONP 方式），这样在 file:// 协议下也能通过 <script> 标签加载
    # 避免 fetch() 在本地文件协议下被 CORS 策略阻止的问题
    js_content = "window.__SEARCH_INDEX__=" + json.dumps(
        docs, ensure_ascii=False, separators=(",", ":")
    ) + ";"
    (output_dir / "search-index.js").write_text(js_content, encoding="utf-8")
    return docs


_SEARCH_SCRIPT = """  <script src="assets/vendor/minisearch.min.js"></script>
  <script src="search-index.js"></script>
  <script>
    (function () {
      var input = document.getElementById("search-input");
      var resultsEl = document.getElementById("search-results");
      var statusEl = document.getElementById("search-status");
      var countEl = document.getElementById("search-count");
      var docs = window.__SEARCH_INDEX__ || [];
      var mini = null;

      function escapeHtml(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
          return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
        });
      }

      function highlight(text, query) {
        var safe = escapeHtml(text);
        if (!query) return safe;
        var q = query.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
        var re = new RegExp("(" + q + ")", "gi");
        return safe.replace(re, '<mark>$1</mark>');
      }

      function snippet(abstract, query, len) {
        if (!abstract) return "";
        var text = abstract;
        var q = (query || "").toLowerCase();
        var pos = text.toLowerCase().indexOf(q);
        if (pos < 0) {
          return text.length > len ? text.slice(0, len) + "…" : text;
        }
        var start = Math.max(0, pos - Math.floor((len - q.length) / 2));
        var end = Math.min(text.length, start + len);
        var prefix = start > 0 ? "…" : "";
        var suffix = end < text.length ? "…" : "";
        return prefix + text.slice(start, end) + suffix;
      }

      function tierClass(tier) {
        if (!tier) return "tier-default";
        if (tier.indexOf("重点") >= 0 || tier.indexOf("必读") >= 0) return "tier-top";
        if (tier.indexOf("推荐") >= 0) return "tier-rec";
        return "tier-default";
      }

      function resultLink(doc) {
        if (doc.report_file) {
          return doc.report_file + (doc.anchor ? "#" + doc.anchor : "");
        }
        return doc.url || "#";
      }

      function renderResult(doc, query) {
        var title = doc.title_zh || doc.title || "(无标题)";
        var sub = doc.title && doc.title !== title ? doc.title : "";
        var meta = [];
        if (doc.journal) meta.push(escapeHtml(doc.journal));
        if (doc.date) meta.push(escapeHtml(doc.date));
        if (doc.primary_category) meta.push(escapeHtml(doc.primary_category));
        var tierHtml = doc.recommendation_tier
          ? '<span class="search-tier ' + tierClass(doc.recommendation_tier) + '">' + escapeHtml(doc.recommendation_tier) + '</span>'
          : "";
        var scoreHtml = doc.total_score != null
          ? '<span class="search-score">评分 ' + Number(doc.total_score).toFixed(1) + '</span>'
          : "";
        var snip = snippet(doc.abstract, query, 160);
        var subHtml = sub ? '<div class="search-sub">' + highlight(sub, query) + '</div>' : "";

        var favId = doc.id || "";
        var favTitle = doc.title_zh || doc.title || "";
        var favUrl = resultLink(doc);
        var favMarkdown = "**" + favTitle + "**";
        if (doc.journal) favMarkdown += "\\n- 期刊: " + doc.journal;
        if (doc.date) favMarkdown += "\\n- 日期: " + doc.date;
        if (doc.total_score != null) favMarkdown += "\\n- 评分: " + Number(doc.total_score).toFixed(1);
        if (doc.recommendation_tier) favMarkdown += "\\n- 推荐等级: " + doc.recommendation_tier;
        if (doc.url) favMarkdown += "\\n- 原文链接: " + doc.url;

        var favBtn = '<button class="favorite-toggle" type="button" data-favorite-toggle aria-pressed="false">'
          + '<img src="assets/icons/folder.svg" alt="">'
          + '<span>收藏</span></button>';

        return '<article class="search-result article-card"'
          + ' data-favorite-id="' + escapeHtml(favId) + '"'
          + ' data-favorite-title="' + escapeHtml(favTitle) + '"'
          + ' data-favorite-url="' + escapeHtml(favUrl) + '"'
          + ' data-favorite-markdown="' + escapeHtml(favMarkdown) + '"'
          + '>'
          + '<div class="search-result-head">'
          + '<h3><a href="' + escapeHtml(favUrl) + '">' + highlight(title, query) + '</a></h3>'
          + '<span class="article-card-actions">' + tierHtml + scoreHtml + favBtn + '</span>'
          + '</div>'
          + subHtml
          + '<div class="search-meta">' + meta.join(' · ') + '</div>'
          + '<p class="search-snippet">' + highlight(snip, query) + '</p>'
          + '</article>';
      }

      function runSearch(query) {
        query = (query || "").trim();
        if (!query) {
          resultsEl.innerHTML = "";
          countEl.textContent = "";
          statusEl.textContent = "输入关键词搜索论文（支持中英文标题、摘要、期刊、分类）";
          return;
        }

        var matches = [];
        if (mini && typeof MiniSearch !== "undefined") {
          matches = mini.search(query);
        } else {
          // Fallback: substring match when MiniSearch is unavailable.
          var lower = query.toLowerCase();
          matches = docs.filter(function (doc) {
            return [doc.title, doc.title_zh, doc.abstract, doc.journal, doc.primary_category, doc.domain]
              .some(function (field) { return field && field.toLowerCase().indexOf(lower) >= 0; });
          });
        }

        countEl.textContent = "共 " + matches.length + " 条结果";
        if (!matches.length) {
          resultsEl.innerHTML = '<p class="search-empty">未找到匹配的论文。</p>';
          return;
        }
        resultsEl.innerHTML = matches.map(function (m) {
          return renderResult(m, query);
        }).join("");
      }

      function initMini() {
        if (typeof MiniSearch === "undefined") return;
        mini = new MiniSearch({
          fields: ['title', 'title_zh', 'abstract', 'journal', 'primary_category', 'domain'],
          storeFields: ['title', 'title_zh', 'abstract', 'journal', 'date', 'url', 'report_file', 'recommendation_tier', 'total_score', 'primary_category', 'domain', 'anchor'],
          searchOptions: {
            boost: { title: 2, title_zh: 2 },
            fuzzy: 0.2,
            prefix: true
          }
        });
        mini.addAll(docs);
      }

      // 索引通过 <script src="search-index.js"> 同步加载，无需 fetch
      if (docs.length > 0) {
        initMini();
        statusEl.textContent = "索引已就绪，共 " + docs.length + " 篇论文。输入关键词开始搜索。";
        var initial = input.value.trim();
        if (initial) runSearch(initial);
      } else {
        statusEl.textContent = "索引加载失败，请刷新重试。";
      }

      var debounceTimer = null;
      input.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () { runSearch(input.value); }, 180);
      });

      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          clearTimeout(debounceTimer);
          runSearch(input.value);
        }
      });

      if (window.location.hash) {
        var hashQuery = decodeURIComponent(window.location.hash.slice(1));
        if (hashQuery) input.value = hashQuery;
      }
    })();
  </script>
"""


def render_search_page(output_dir: Path) -> None:
    """Write docs/search.html with a MiniSearch powered search UI."""
    body = """
<h1>搜索论文</h1>
<div class="search-box">
  <input id="search-input" type="search" placeholder="输入关键词，如：星形胶质细胞 / microglia / 睡眠" autocomplete="off" autofocus>
  <p id="search-status" class="meta">正在加载索引…</p>
  <p id="search-count" class="search-count"></p>
</div>
<section id="search-results" class="search-results"></section>
"""
    # render_page returns a full HTML document; splice the search script in before </body>.
    html_content = render_page("搜索论文", body).replace(
        "</body>",
        _SEARCH_SCRIPT + "</body>",
    )
    (output_dir / "search.html").write_text(html_content, encoding="utf-8")
