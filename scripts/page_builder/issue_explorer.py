"""Single-issue reading explorer, derived only from identity-aligned local evaluations."""
from __future__ import annotations

from collections import Counter
import html
import json
import math
from pathlib import Path

from .articles import article_title_and_url, is_article_heading
from .core import report_date_from_name
from .sources import article_link_from_raw_data, normalize_title_key


def report_titles(markdown: str) -> set[str]:
    lines = markdown.splitlines()
    return {normalize_title_key(article_title_and_url(lines[i])[0])
            for i in range(len(lines)) if is_article_heading(lines, i)}


def result_title(item: dict) -> str:
    paper = item.get('paper') or {}
    return str((paper.get('raw_data') or {}).get('title') or paper.get('title') or '')


def aligned_results(input_dir: Path, report_path: Path, markdown: str) -> tuple[Path, list[dict]] | None:
    """Require a complete, unambiguous title-set match, allowing legacy one-day offsets.

    Title matching pairs a report with its own corpus; it never merges paper identities.
    Ambiguous title variants or duplicate records fail closed instead of inflating counts.
    """
    from datetime import datetime, timedelta
    titles = report_titles(markdown)
    if not titles:
        return None
    day = datetime.strptime(report_date_from_name(report_path), '%Y-%m-%d')
    for offset in (0, -1, 1):
        candidates = []
        stamp = (day + timedelta(days=offset)).strftime('%Y%m%d')
        for path in sorted(input_dir.glob(f'LLM_results_{stamp}*.json')):
            if any(token in path.name.lower() for token in ('wechat', 'specialissue', '.raw', '.deprecated')):
                continue
            values = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(values, list):
                continue
            keys = [normalize_title_key(result_title(item)) for item in values]
            if len(keys) == len(set(keys)) and titles.issubset(set(keys)):
                candidates.append((path, values))
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return None
    return None


def explorer_payload(input_dir: Path, report_path: Path, markdown: str) -> dict | None:
    aligned = aligned_results(input_dir, report_path, markdown)
    if aligned is None:
        return None
    source, results = aligned
    expanded = report_titles(markdown)
    rows = []
    for item in results:
        if item.get('domain') == '域外局限':
            continue
        title = result_title(item)
        raw = (item.get('paper') or {}).get('raw_data') or {}
        score = item.get('total_score')
        if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 10:
            score = None
        field = item.get('primary_category')
        if not field or field == 'None':
            field = '域外高影响（未分领域）' if item.get('domain') == '域外高影响' else '未分领域'
        tags = item.get('cross_tags') or []
        if not isinstance(tags, list):
            tags = []
        rows.append({
            'title': title, 'titleZh': item.get('title_zh') or title,
            'url': article_link_from_raw_data(raw, title), 'score': score,
            'field': str(field), 'tier': item.get('recommendation_tier') or '未分级',
            'tags': sorted({str(tag).strip() for tag in tags if str(tag).strip()}),
            'summary': item.get('recommendation_text') or item.get('feature_angle') or '',
            'expanded': normalize_title_key(title) in expanded,
        })
    return {'source': source.name, 'date': report_date_from_name(report_path),
            'evaluated': len(results), 'excluded': len(results) - len(rows), 'rows': rows}


def render_issue_explorer(payload: dict) -> str:
    rows = payload['rows']
    field_counts = Counter(row['field'] for row in rows)
    fields = ''.join(f'<tr><td>{html.escape(field)}</td><td>{count}</td></tr>'
                     for field, count in field_counts.most_common())
    raw_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return f'''<section class="issue-explorer" id="issue-explorer" aria-label="本期阅读导航">
<div class="issue-heading"><div><span class="issue-eyebrow">ISSUE EXPLORER · {payload['date']}</span><h2>本期阅读导航</h2></div><a href="#issue-reading-results">浏览文章 ↓</a></div>
<div class="issue-metrics"><div><strong>{payload['evaluated']}</strong><span>检索并评估</span></div><div><strong>{len(rows)}</strong><span>进入本期统计</span></div><div><strong>{sum(row['expanded'] for row in rows)}</strong><span>正文展开文章</span></div><div><strong>{len(field_counts)}</strong><span>领域及未分类组</span></div></div>
<p class="issue-scope-note">统计排除“域外局限” {payload['excluded']} 篇；按主领域每篇计一次。无主领域的文章单列，主题词按含该标签的文章数计次。</p>
<div class="issue-toolbar"><label>阅读范围 <select id="issue-scope"><option value="all">全部统计文章（{len(rows)} 篇）</option><option value="expanded">正文推荐文章（{sum(row['expanded'] for row in rows)} 篇）</option></select></label><button type="button" id="issue-reset">清除筛选</button><span id="issue-status" role="status" aria-live="polite"></span></div>
<div class="issue-chart-grid"><div class="issue-chart-card"><h3>评分分布 <small>按研究领域堆叠</small></h3><div id="issue-score-chart" class="issue-chart" role="img" aria-label="评分区间及领域构成"></div></div><div class="issue-chart-card"><h3>领域分布 <small>按评分段堆叠</small></h3><div id="issue-field-chart" class="issue-chart" role="img" aria-label="研究领域及评分构成"></div></div></div>
<p class="issue-hint">点击柱形色块筛选文章；可在下方叠加领域、评分和主题条件。评分为策展模型评分，评分段不等同推荐等级。</p>
<div class="issue-topics"><h3>本期主题词 <small>字号表示文章频次</small></h3><div id="issue-topic-cloud" aria-label="可筛选的主题词"></div></div>
<details id="issue-reading-results"><summary class="issue-results-head"><strong>文章索引</strong><span id="issue-result-count" aria-live="polite"></span><span class="issue-index-toggle" aria-hidden="true"></span></summary><div class="issue-filter-row"><label>研究领域 <select id="issue-field"><option value="">全部领域</option></select></label><label>评分区间 <select id="issue-score"><option value="">全部评分</option></select></label><label>搜索文章 <input id="issue-query" type="search" placeholder="标题、主题词或推荐理由"></label></div><div id="issue-result-list"></div><div class="issue-pagination"><button type="button" id="issue-prev">上一页</button><span id="issue-page"></span><button type="button" id="issue-next">下一页</button></div></details>
<details class="issue-data-details"><summary>统计明细与来源</summary><p>数据来源：{html.escape(payload['source'])}。两图与主题词随阅读范围切换；图表点击仅筛选文章索引，保留全范围分布作参照。评分区间左闭右开，最后一档包含 10；领域图按 ≤7、7–9（不含7）、&gt;9 分组，缺失评分单列。“其他领域”可通过领域下拉框继续细分。</p><div id="issue-data-table"><table><thead><tr><th>主领域</th><th>篇数</th></tr></thead><tbody>{fields}</tbody></table></div></details>
<noscript><p>交互图表需要 JavaScript。正文和统计明细仍可直接阅读。</p></noscript>
<script type="application/json" id="issue-explorer-data">{raw_json}</script>
</section>'''
