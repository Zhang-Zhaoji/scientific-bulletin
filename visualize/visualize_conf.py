"""
Visualize ICLR/ICML conference paper data from OpenReview.

Generates:
1. Country distribution bar chart + choropleth map
2. Institution top-N bar chart
3. Keyword word cloud
4. Recommendation tier pie chart

Usage:
  python visualize_conf.py --llm LLM_Results/LLM_results_iclr2025.json --papers getfiles/iclr2025_papers.jsonl
  python visualize_conf.py --llm LLM_Results/LLM_results_icml2025.json --papers getfiles/icml2025_papers.jsonl
"""
import json
import argparse
import os
import textwrap
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import jsonlines
try:
    from wordcloud import WordCloud
except ImportError:
    WordCloud = None

# Clean sans-serif font
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BASE_OUTPUT_DIR = Path('./Imgs/conf_visualization')
BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = BASE_OUTPUT_DIR  # Set per-conference in main()

# ── Domain TLD → Country mapping ──
TLD_TO_COUNTRY = {
    'cn': 'China', 'hk': 'Hong Kong', 'tw': 'Taiwan', 'jp': 'Japan',
    'kr': 'South Korea', 'sg': 'Singapore', 'in': 'India', 'th': 'Thailand',
    'au': 'Australia', 'nz': 'New Zealand',
    'uk': 'United Kingdom', 'ie': 'Ireland', 'fr': 'France', 'de': 'Germany',
    'it': 'Italy', 'es': 'Spain', 'pt': 'Portugal', 'nl': 'Netherlands',
    'be': 'Belgium', 'ch': 'Switzerland', 'at': 'Austria', 'se': 'Sweden',
    'no': 'Norway', 'dk': 'Denmark', 'fi': 'Finland', 'pl': 'Poland',
    'cz': 'Czech Republic', 'gr': 'Greece', 'hu': 'Hungary', 'ro': 'Romania',
    'ru': 'Russia', 'ua': 'Ukraine', 'tr': 'Turkey', 'il': 'Israel',
    'sa': 'Saudi Arabia', 'ae': 'UAE', 'ir': 'Iran',
    'ca': 'Canada', 'mx': 'Mexico', 'br': 'Brazil', 'ar': 'Argentina',
    'cl': 'Chile', 'co': 'Colombia',
    'za': 'South Africa', 'eg': 'Egypt', 'ng': 'Nigeria',
    'edu': 'United States', 'com': 'United States', 'org': 'United States',
}

# Country name → ISO-3 code for plotly choropleth
COUNTRY_TO_ISO = {
    'China': 'CHN', 'Hong Kong': 'HKG', 'Taiwan': 'TWN', 'Japan': 'JPN',
    'South Korea': 'KOR', 'Singapore': 'SGP', 'India': 'IND', 'Thailand': 'THA',
    'Australia': 'AUS', 'New Zealand': 'NZL',
    'United Kingdom': 'GBR', 'Ireland': 'IRL', 'France': 'FRA', 'Germany': 'DEU',
    'Italy': 'ITA', 'Spain': 'ESP', 'Portugal': 'PRT', 'Netherlands': 'NLD',
    'Belgium': 'BEL', 'Switzerland': 'CHE', 'Austria': 'AUT', 'Sweden': 'SWE',
    'Norway': 'NOR', 'Denmark': 'DNK', 'Finland': 'FIN', 'Poland': 'POL',
    'Czech Republic': 'CZE', 'Greece': 'GRC', 'Hungary': 'HUN', 'Romania': 'ROU',
    'Russia': 'RUS', 'Ukraine': 'UKR', 'Turkey': 'TUR', 'Israel': 'ISR',
    'Saudi Arabia': 'SAU', 'UAE': 'ARE', 'Iran': 'IRN',
    'United States': 'USA', 'Canada': 'CAN', 'Mexico': 'MEX',
    'Brazil': 'BRA', 'Argentina': 'ARG', 'Chile': 'CHL', 'Colombia': 'COL',
    'South Africa': 'ZAF', 'Egypt': 'EGY', 'Nigeria': 'NGA',
}


def domain_to_country(domain: str) -> str:
    """Map an institution domain to a country name."""
    if not domain:
        return 'Unknown'
    domain = domain.lower().strip()
    parts = domain.split('.')
    # Try from the most specific TLD
    for part in reversed(parts):
        if part in TLD_TO_COUNTRY:
            return TLD_TO_COUNTRY[part]
        if part == 'ac':
            # academic domain, check next part
            continue
    return 'Unknown'


def load_llm_results(path: str) -> list:
    """Load LLM analysis results."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_papers(path: str) -> list:
    """Load crawled papers from JSONL."""
    with jsonlines.open(path) as reader:
        return list(reader)


def match_papers(llm_results: list, papers: list) -> list:
    """Match LLM results with crawled papers by title, return merged list."""
    paper_by_title = {}
    for p in papers:
        title = p.get('title', '').strip().lower()
        if title:
            paper_by_title[title] = p

    merged = []
    for result in llm_results:
        title = result.get('paper', {}).get('title', '').strip().lower()
        raw = result.get('paper', {}).get('raw_data', {})
        # Try matching by forum_id first
        forum_id = raw.get('forum_id', '')
        matched = None
        for p in papers:
            if p.get('forum_id') == forum_id:
                matched = p
                break
        if not matched:
            matched = paper_by_title.get(title)
        if matched:
            merged.append({**result, '_paper_data': matched})
        else:
            merged.append(result)
    return merged


def extract_countries(merged: list, filter_tiers=None) -> Counter:
    """Extract country distribution from author affiliations."""
    if filter_tiers:
        merged = [m for m in merged if m.get('recommendation_tier') in filter_tiers]

    country_counter = Counter()
    for item in merged:
        paper = item.get('_paper_data')
        if not paper:
            continue
        affs = paper.get('author_affiliations', [])
        paper_countries = set()
        for author_affs in affs:
            if not isinstance(author_affs, list):
                continue
            # Only look at current affiliation (end is None or 'present')
            for aff in author_affs:
                if not isinstance(aff, dict):
                    continue
                # Include all affiliations (not just current)
                domain = aff.get('domain', '')
                country = domain_to_country(domain)
                if country != 'Unknown':
                    paper_countries.add(country)
        for c in paper_countries:
            country_counter[c] += 1
    return country_counter


import re

# Stopwords ignored when comparing institution name word sets
_STOPWORDS = {'the', 'of', 'and', 'for', 'at', 'in', 'a', 'an'}

# Manual alias map: canonical name → set of aliases (all will be merged into canonical)
INSTITUTION_ALIASES = {
    'Beihang University': {
        'Beijing University of Aeronautics and Astronautics',
        'Beihang',
    },
    'Shanghai Jiao Tong University': {
        'Shanghai Jiaotong University',
        'Shanghai Jiao Tong University',
    },
}

# Companies whose country should be China
CHINA_COMPANIES = {
    'alibaba', 'huawei', 'bytedance', 'baidu', 'tencent',
    'alibaba group', 'huawei technologies', 'bytedance ltd',
    'tencent ai lab', 'baidu inc', 'alibaba damo academy',
}

# Institution name → country overrides (for names where domain-based detection fails)
INSTITUTION_COUNTRY_OVERRIDE = {
    'chinese academy of sciences': 'China',
    'chinese academy of science': 'China',
    'eth zurich': 'Switzerland',
    'ethz': 'Switzerland',
    'ethz-eth zurich': 'Switzerland',
    'eth zürich': 'Switzerland',
    'eth': 'Switzerland',
}

# Prefixes that indicate a department/school, not an institution
_NON_INST_PREFIXES = ['department of', 'school of', 'division of', 'faculty of']


def _is_non_institution(name: str) -> bool:
    """Check if name is a department/school rather than a real institution."""
    name_lower = name.lower().strip()
    if ',' in name_lower:
        return False  # Comma-separated names may merge into parent
    for prefix in _NON_INST_PREFIXES:
        if name_lower.startswith(prefix):
            # Keep if it also contains university/institute/college etc.
            if any(kw in name_lower for kw in ['university', 'institute', 'college', 'laboratory', 'hospital']):
                return False
            return True
    return False


def _normalize_name(name: str) -> frozenset:
    """Normalize institution name to a frozenset of lowercase words (no punctuation, no stopwords)."""
    # Remove all non-alphanumeric except spaces
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', name.lower())
    words = set(cleaned.split()) - _STOPWORDS
    return frozenset(words)


def _dedup_institution_name(name: str) -> str:
    """Merge duplicate comma-separated parts and apply alias mapping."""
    # First: split by comma, remove exact duplicates
    parts = [p.strip() for p in name.split(',')]
    seen = set()
    unique = []
    for p in parts:
        if p and p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)
    name = ', '.join(unique) if len(unique) > 1 else (unique[0] if unique else name)

    # Then: check manual alias map
    name_lower = name.lower().strip()
    for canonical, aliases in INSTITUTION_ALIASES.items():
        if name_lower == canonical.lower():
            return canonical
        for alias in aliases:
            if name_lower == alias.lower():
                return canonical

    return name


def _resolve_alias_by_fuzzy(name: str, existing_names: list, existing_norms: dict) -> str:
    """Check if name fuzzy-matches an existing institution.
    Only matches on EXACT word set (after removing punctuation/stopwords, ignoring order).
    Returns the canonical name if match found, otherwise the original name."""
    norm = _normalize_name(name)
    if not norm:
        return name

    # Check exact set match only (safe: "Microsoft, Research" == "Research Microsoft")
    if norm in existing_norms:
        return existing_norms[norm]

    return name


def extract_institutions(merged: list, filter_tiers=None, top_n=20) -> list:
    """Extract institution distribution with fuzzy dedup and country mapping."""
    if filter_tiers:
        merged = [m for m in merged if m.get('recommendation_tier') in filter_tiers]

    # First pass: collect raw (name, domain) pairs
    raw_pairs = []
    for item in merged:
        paper = item.get('_paper_data')
        if not paper:
            continue
        affs = paper.get('author_affiliations', [])
        paper_insts = {}  # name -> domain
        for author_affs in affs:
            if not isinstance(author_affs, list):
                continue
            for aff in author_affs:
                if not isinstance(aff, dict):
                    continue
                name = aff.get('name', '').strip()
                if name:
                    name = _dedup_institution_name(name)
                    # Skip non-institution names (departments, schools)
                    if _is_non_institution(name):
                        continue
                    paper_insts[name] = aff.get('domain', '')
        for inst, domain in paper_insts.items():
            raw_pairs.append((inst, domain))

    # Second pass: fuzzy match and merge
    inst_counter = Counter()
    inst_country = {}
    existing_norms = {}  # normalized frozenset -> canonical name

    for name, domain in raw_pairs:
        # Check fuzzy match against existing
        canonical = _resolve_alias_by_fuzzy(name, list(inst_counter.keys()), existing_norms)
        if canonical not in existing_norms.values() and canonical == name:
            # New institution, register its norm
            existing_norms[_normalize_name(canonical)] = canonical

        inst_counter[canonical] += 1
        country = domain_to_country(domain)
        # Override country for known Chinese companies
        if any(cc in name.lower() for cc in CHINA_COMPANIES):
            country = 'China'
        # Override country for specific institutions by name
        name_lower = canonical.lower().strip()
        for inst_key, inst_country_name in INSTITUTION_COUNTRY_OVERRIDE.items():
            if inst_key in name_lower:
                country = inst_country_name
                break
        if canonical not in inst_country:
            inst_country[canonical] = Counter()
        inst_country[canonical][country] += 1

    # Post-pass: merge comma-separated names where one part matches an existing institution
    # e.g. "School of Computer Science, Carnegie Mellon University" → "Carnegie Mellon University"
    single_names = {n for n in inst_counter if ',' not in n}
    to_merge = {}
    for name in list(inst_counter.keys()):
        if ',' not in name:
            continue
        # Exception: keep "University of California, Berkeley" etc.
        if 'university of california' in name.lower():
            continue
        parts = [p.strip() for p in name.split(',')]
        for part in parts:
            # Check exact case-insensitive match against single-part names
            for sn in single_names:
                if part.lower() == sn.lower():
                    to_merge[name] = sn
                    break
            if name in to_merge:
                break

    for comma_name, single_name in to_merge.items():
        if comma_name == single_name:
            continue
        inst_counter[single_name] += inst_counter[comma_name]
        if comma_name in inst_country:
            if single_name not in inst_country:
                inst_country[single_name] = Counter()
            inst_country[single_name] += inst_country[comma_name]
            del inst_country[comma_name]
        del inst_counter[comma_name]

    top = inst_counter.most_common(top_n)
    result = []
    for name, count in top:
        country = inst_country.get(name, Counter()).most_common(1)[0][0] if inst_country.get(name) else 'Unknown'
        result.append((name, count, country))
    return result


def extract_keywords(merged: list, filter_tiers=None) -> Counter:
    """Extract keyword frequency. English keywords are uppercased."""
    if filter_tiers:
        merged = [m for m in merged if m.get('recommendation_tier') in filter_tiers]

    kw_counter = Counter()
    for item in merged:
        # Keywords from raw_data (English, from OpenReview)
        raw = item.get('paper', {}).get('raw_data', {})
        keywords = raw.get('keywords', [])
        for kw in keywords:
            kw = kw.strip()
            if kw and len(kw) > 1:
                kw_counter[kw.upper()] += 1
        # Also count cross_tags from LLM (may be Chinese)
        tags = item.get('cross_tags', [])
        for tag in tags:
            tag = tag.strip()
            if tag and len(tag) > 1:
                kw_counter[tag.upper()] += 1
    return kw_counter


def _prepare_treemap_data(counter: Counter, top_n: int) -> tuple:
    """Prepare data for treemap: top N items + OTHERS."""
    top = counter.most_common(top_n)
    if not top:
        return [], []
    total = sum(counter.values())
    others = total - sum(c for _, c in top)
    labels = [name.upper() for name, _ in top]
    sizes = [count for _, count in top]
    if others > 0:
        labels.append('OTHERS')
        sizes.append(others)
    return labels, sizes


def _prepare_pie_data(counter: Counter, top_n: int) -> tuple:
    """Prepare data for pie chart: top N items + OTHERS."""
    return _prepare_treemap_data(counter, top_n)


_DARK_PALETTE = ['#1B3A5C', '#B83227', '#2C6E49', '#5B2C6F', '#7D6608',
                 '#6E2C00', '#922B21', '#34495E', '#1A5276', '#A04000',
                 '#196F3D', '#5D6D7E', '#7D3C98', '#B03A2E', '#1F618D',
                 '#117864', '#5B2C6F', '#1E8449', '#943126', '#154360',
                 '#0E6255', '#512E5F', '#641E16', '#239B56', '#17202A']


def _get_chart_colors(names: list, country_map: dict = None) -> list:
    """Get editorial dark colors for a list of names. Uses country_map if available."""
    colors = []
    for i, name in enumerate(names):
        # Try country color map first (for institution charts)
        if country_map and name in country_map:
            colors.append(country_map[name])
        elif name in COUNTRY_COLORS:
            colors.append(COUNTRY_COLORS[name])
        else:
            colors.append(_DARK_PALETTE[i % len(_DARK_PALETTE)])
    return colors


def plot_country_treemap(country_counter: Counter, title: str, top_n=30):
    """Treemap of top N countries with gaps between rectangles."""
    import squarify

    labels, sizes = _prepare_treemap_data(country_counter, top_n)
    if not labels:
        print(f"  [WARN] No country data for treemap")
        return

    # Map labels back to country names for color lookup
    label_to_country = {l: l.title() for l in labels if l != 'OTHERS'}
    colors = [_get_country_color(label_to_country.get(l, l)) if l != 'OTHERS' else '#7F8C8D' for l in labels]
    fig, ax = plt.subplots(figsize=(14, 8))
    squarify.plot(
        sizes=sizes, label=labels, color=colors, alpha=0.85,
        text_kwargs={'fontsize': 8, 'fontweight': 'bold'},
        ax=ax, ec='white', linewidth=2,
    )
    ax.set_title(f'{title} — Country/Region Distribution (Top {top_n})', fontsize=14, fontweight='bold')
    ax.axis('off')
    plt.tight_layout()
    path = OUTPUT_DIR / 'country_treemap.png'
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


def plot_country_pie(country_counter: Counter, title: str, top_n=10):
    """Pie chart of top N countries with gaps between wedges."""
    labels, sizes = _prepare_pie_data(country_counter, top_n)
    if not labels:
        print(f"  [WARN] No country data for pie chart")
        return

    label_to_country = {l: l.title() for l in labels if l != 'OTHERS'}
    colors = [_get_country_color(label_to_country.get(l, l)) if l != 'OTHERS' else '#7F8C8D' for l in labels]
    fig, ax = plt.subplots(figsize=(10, 8))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct='%1.1f%%', colors=colors,
        startangle=140, textprops={'fontsize': 9, 'fontweight': 'bold'},
        pctdistance=0.8,
        wedgeprops={'edgecolor': 'white', 'linewidth': 2},
    )
    ax.set_title(f'{title} — Country/Region Share (Top {top_n})', fontsize=14, fontweight='bold')
    plt.tight_layout()
    path = OUTPUT_DIR / 'country_pie.png'
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


def plot_country_choropleth(country_counter: Counter, title: str):
    """Interactive choropleth map using plotly."""
    try:
        import plotly.express as px
        import pandas as pd

        data = []
        for country, count in country_counter.most_common():
            iso = COUNTRY_TO_ISO.get(country)
            if iso:
                data.append({'country': country.upper(), 'iso': iso, 'count': count})

        if not data:
            print(f"  [WARN] No ISO-mapped countries for choropleth")
            return

        df = pd.DataFrame(data)
        fig = px.choropleth(
            df, locations='iso', color='count',
            hover_name='country',
            color_continuous_scale='YlOrRd',
            title=f'{title} - Global Distribution',
            labels={'count': 'Paper Count'},
        )
        fig.update_layout(geo=dict(showframe=False, showcoastlines=True, projection_type='natural earth'))
        path = OUTPUT_DIR / 'choropleth.html'
        fig.write_html(str(path))
        print(f"  Saved: {path}")
    except Exception as e:
        print(f"  [WARN] Choropleth failed: {e}")


# Editorial dark color palette (inspired by The Economist / FT)
# Hong Kong uses same color as China
COUNTRY_COLORS = {
    'United States': '#1B3A5C', 'China': '#B83227', 'United Kingdom': '#2C6E49',
    'Canada': '#5B2C6F', 'Germany': '#7D6608', 'France': '#6E2C00',
    'Switzerland': '#922B21', 'Japan': '#34495E', 'South Korea': '#1A5276',
    'Australia': '#A04000', 'Singapore': '#196F3D', 'Hong Kong': '#B83227',
    'Netherlands': '#5D6D7E', 'Israel': '#7D3C98', 'India': '#B03A2E',
    'Italy': '#1F618D', 'Spain': '#117864', 'Sweden': '#5B2C6F',
    'Taiwan': '#B83227', 'Brazil': '#1E8449', 'Unknown': '#7F8C8D',
}


def _get_country_color(country: str) -> str:
    """Get color for a country, default to light gray."""
    return COUNTRY_COLORS.get(country, '#7F8C8D')


# Prepositions that should stay with the next word (no line break after)
_PREPOSITIONS = {'of', 'at', 'for', 'in', 'and', 'de', 'du', 'la', 'le', 'et', 'the'}

# Multi-word proper nouns that should never be split across lines
_MULTIWORD = ['HONG KONG', 'NEW YORK', 'SAN FRANCISCO', 'LOS ANGELES', 'UNITED STATES',
              'UNITED KINGDOM', 'SOUTH KOREA', 'SAUDI ARABIA', 'NEW ZEALAND']


def _wrap_label(text: str, width: int = 18) -> str:
    """Smart wrap: keep prepositions with next word, keep multi-word names together."""
    if not text:
        return text

    words = text.split()
    # Join prepositions with the following word using non-breaking space
    units = []
    i = 0
    while i < len(words):
        if i + 1 < len(words) and words[i].lower() in _PREPOSITIONS:
            units.append(words[i] + '\u00A0' + words[i+1])
            i += 2
        else:
            units.append(words[i])
            i += 1

    # Join multi-word proper nouns
    joined = ' '.join(units)
    for mw in _MULTIWORD:
        joined = joined.replace(mw, mw.replace(' ', '\u00A0'))

    # Wrap
    wrapped = textwrap.fill(joined, width=width, break_long_words=False)
    # Convert non-breaking spaces back to regular spaces for display
    return wrapped.replace('\u00A0', ' ')


def _per_country_coverage(institutions: list, target: float = 0.90) -> dict:
    """Group institutions by country, for each country keep top institutions covering ~90%.
    Returns {country: [(name, count, country), ...]} with a trailing 'COUNTRY (OTHERS)' entry."""
    by_country = {}
    for name, count, country in institutions:
        by_country.setdefault(country, []).append((name, count, country))

    result = {}
    for country, insts in by_country.items():
        insts.sort(key=lambda x: -x[1])
        total = sum(c for _, c, _ in insts)
        cumulative = 0
        cutoff = len(insts)
        for i, (_, count, _) in enumerate(insts):
            cumulative += count
            if cumulative / total >= target:
                cutoff = i + 1
                break
        top = insts[:cutoff]
        rest_count = sum(c for _, c, _ in insts[cutoff:])
        if rest_count > 0:
            label = 'UNKNOWN' if country == 'Unknown' else f'{country.upper()} (OTHERS)'
            top.append((label, rest_count, country))
        result[country] = top
    return result


def plot_institution_treemap(institutions: list, title: str, top_n=None):
    """Hierarchical treemap: country blocks → institution sub-blocks.
    Per-country 90% coverage, COUNTRY (OTHERS) / UNKNOWN labels."""
    import squarify
    from matplotlib.patches import Patch, Rectangle

    if not institutions:
        print(f"  [WARN] No institution data for treemap")
        return

    # 1) Per-country 90% coverage
    by_country = _per_country_coverage(institutions, target=0.90)

    # 2) Country-level sizes (sum of all entries per country)
    country_sizes = []
    for country, entries in by_country.items():
        total = sum(c for _, c, _ in entries)
        country_sizes.append((country, total))
    country_sizes.sort(key=lambda x: (-x[1] if x[0] != 'Unknown' else 0))

    # Limit to top ~15 countries for readability
    max_countries = 15
    shown_countries = country_sizes[:max_countries]
    hidden_total = sum(s for _, s in country_sizes[max_countries:])

    # 3) Layout country blocks with squarify
    sizes = [s for _, s in shown_countries]
    if hidden_total > 0:
        sizes.append(hidden_total)
    norm_sizes = squarify.normalize_sizes(sizes, 100, 100)
    country_rects = squarify.squarify(norm_sizes, 0, 0, 100, 100)

    fig, ax = plt.subplots(figsize=(16, 9))

    # 4) For each country block, sub-divide into institutions
    for rect, (country, _) in zip(country_rects, shown_countries):
        entries = by_country.get(country, [])
        base_color = _get_country_color(country)

        if not entries:
            continue

        sub_sizes = [c for _, c, _ in entries]
        sub_norm = squarify.normalize_sizes(sub_sizes, rect['dx'], rect['dy'])
        sub_rects = squarify.squarify(sub_norm, rect['x'], rect['y'], rect['dx'], rect['dy'])

        # Draw country border (slightly larger, lighter)
        ax.add_patch(Rectangle(
            (rect['x'], rect['y']), rect['dx'], rect['dy'],
            facecolor='none', edgecolor='white', linewidth=4,
        ))

        # Draw institution sub-blocks
        for sub_rect, (name, count, _) in zip(sub_rects, entries):
            is_others = '(OTHERS)' in name or name == 'UNKNOWN'
            # Slightly lighter shade for OTHERS blocks
            if is_others:
                # Use a lighter version of the country color
                color = base_color
                alpha = 0.45
            else:
                color = base_color
                alpha = 0.85

            ax.add_patch(Rectangle(
                (sub_rect['x'], sub_rect['y']), sub_rect['dx'], sub_rect['dy'],
                facecolor=color, edgecolor='white', linewidth=1.5, alpha=alpha,
            ))

            # Auto-sized text with vertical overflow check
            area = sub_rect['dx'] * sub_rect['dy']
            font_size = max(5, min(14, int(area ** 0.5) * 1.0))
            wrap_width = max(8, int(sub_rect['dx'] / 2.2))
            wrapped = _wrap_label(name.upper(), wrap_width)
            n_lines = wrapped.count('\n') + 1
            # Estimate text height vs rectangle height; shrink font if overflow
            est_height = n_lines * font_size * 0.16  # rough scaling in 0-100 space
            if est_height > sub_rect['dy'] * 0.85:
                font_size = max(5, int(font_size * (sub_rect['dy'] * 0.85 / est_height)))
            if area > 15:  # Only show text for reasonably sized blocks
                ax.text(
                    sub_rect['x'] + sub_rect['dx'] / 2, sub_rect['y'] + sub_rect['dy'] / 2,
                    wrapped, fontsize=font_size, fontweight='bold',
                    ha='center', va='center', color='white',
                )

    # Draw hidden countries as one block
    if hidden_total > 0:
        hidden_rect = country_rects[len(shown_countries)]
        ax.add_patch(Rectangle(
            (hidden_rect['x'], hidden_rect['y']), hidden_rect['dx'], hidden_rect['dy'],
            facecolor='#7F8C8D', edgecolor='white', linewidth=2.5, alpha=0.6,
        ))
        area = hidden_rect['dx'] * hidden_rect['dy']
        if area > 15:
            font_size = max(5, min(14, int(area ** 0.5) * 1.0))
            ax.text(
                hidden_rect['x'] + hidden_rect['dx'] / 2, hidden_rect['y'] + hidden_rect['dy'] / 2,
                'OTHER\nCOUNTRIES', fontsize=font_size, fontweight='bold',
                ha='center', va='center', color='white',
            )

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.invert_yaxis()
    ax.set_title(f'{title} — Institution Distribution by Country (Per-Country 90% Coverage)', fontsize=14, fontweight='bold')
    ax.axis('off')

    # Legend
    legend_countries = [c for c, _ in shown_countries if c != 'Unknown'][:10]
    legend_elements = [Patch(facecolor=_get_country_color(c), edgecolor='white', label=c.upper()) for c in legend_countries]
    if legend_elements:
        ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.02),
                  ncol=min(5, len(legend_elements)), fontsize=7, framealpha=0.9, title='COUNTRY', title_fontsize=8)

    plt.tight_layout()
    path = OUTPUT_DIR / 'institutions_treemap.png'
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


def plot_institution_pie(institutions: list, title: str, top_n=10):
    """Pie chart: per-country 90% coverage, COUNTRY (OTHERS) / UNKNOWN labels."""
    if not institutions:
        print(f"  [WARN] No institution data for pie chart")
        return

    # Per-country 90% coverage
    by_country = _per_country_coverage(institutions, target=0.90)

    # Flatten, sort by count, take top N
    all_entries = []
    for country, entries in by_country.items():
        all_entries.extend(entries)
    all_entries.sort(key=lambda x: -x[1])

    top = all_entries[:top_n]
    rest = all_entries[top_n:]

    labels = [_wrap_label(name.upper(), 22) for name, _, _ in top]
    sizes = [count for _, count, _ in top]
    countries = [country for _, _, country in top]
    if rest:
        labels.append('OTHERS')
        sizes.append(sum(c for _, c, _ in rest))
        countries.append('Unknown')

    colors = [_get_country_color(c) for c in countries]
    fig, ax = plt.subplots(figsize=(11, 9))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct='%1.1f%%', colors=colors,
        startangle=140, textprops={'fontsize': 8, 'fontweight': 'bold'},
        pctdistance=0.8,
        wedgeprops={'edgecolor': 'white', 'linewidth': 2.5},
    )
    ax.set_title(f'{title} — Institution Share by Country', fontsize=14, fontweight='bold')
    plt.tight_layout()
    path = OUTPUT_DIR / 'institutions_pie.png'
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


def plot_wordcloud(keyword_counter: Counter, title: str):
    """Generate word cloud from keywords. Uses CJK-compatible font."""
    if WordCloud is None:
        print("  [SKIP] wordcloud package not installed, skipping word cloud")
        return
    if not keyword_counter:
        print(f"  [WARN] No keywords for word cloud")
        return

    # Find a CJK-compatible font (prefer Microsoft YaHei for cleaner look)
    font_path = None
    for candidate in [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf']:
        if os.path.exists(candidate):
            font_path = candidate
            break

    freq = dict(keyword_counter.most_common(200))
    wc_kwargs = dict(
        width=1200, height=600,
        background_color='white',
        max_words=150,
        colormap='viridis',
        relative_scaling=0.5,
        prefer_horizontal=0.9,
    )
    if font_path:
        wc_kwargs['font_path'] = font_path

    wc = WordCloud(**wc_kwargs).generate_from_frequencies(freq)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    ax.set_title(f'{title} - Keyword Word Cloud', fontsize=16)
    plt.tight_layout()
    path = OUTPUT_DIR / 'wordcloud.png'
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


def plot_tier_pie(merged: list, title: str):
    """Pie chart of recommendation tiers."""
    tier_counter = Counter(m.get('recommendation_tier', 'Unknown') for m in merged)
    if not tier_counter:
        return

    # Map Chinese tier names to English
    TIER_EN = {
        '不推送': 'NOT RECOMMENDED',
        '简要提及': 'BRIEF MENTION',
        '深度解读': 'DEEP ANALYSIS',
        '头条推荐': 'HEADLINE',
        'Unknown': 'UNKNOWN',
    }
    labels = [TIER_EN.get(t, t.upper()) for t in tier_counter.keys()]
    sizes = list(tier_counter.values())
    # Editorial dark colors for tiers
    TIER_COLORS = {
        'NOT RECOMMENDED': '#7F8C8D',  # gray
        'BRIEF MENTION': '#1A5276',    # dark teal
        'DEEP ANALYSIS': '#B83227',    # dark red
        'HEADLINE': '#7D6608',         # dark gold
        'UNKNOWN': '#5D6D7E',          # steel gray
    }
    colors = [TIER_COLORS.get(l, '#5D6D7E') for l in labels]

    fig, ax = plt.subplots(figsize=(8, 8))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct='%1.1f%%', colors=colors[:len(labels)],
        startangle=140, textprops={'fontsize': 11, 'fontweight': 'bold'},
        wedgeprops={'edgecolor': 'white', 'linewidth': 2.5},
    )
    ax.set_title(f'{title} — Recommendation Distribution', fontsize=14, fontweight='bold')
    plt.tight_layout()
    path = BASE_OUTPUT_DIR / title.lower().replace(' ', '_') / 'tier_pie.png'
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"  Saved: {path}")


def run_visualization(merged: list, title: str, filter_tiers=None):
    """Run all visualizations for a given dataset."""
    global OUTPUT_DIR

    is_deep = bool(filter_tiers)
    subdir = 'deep' if is_deep else 'all'
    OUTPUT_DIR = BASE_OUTPUT_DIR / title.lower().replace(' ', '_') / subdir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating visualizations for {title} ({subdir.upper()})...")

    # 1. Country distribution
    print("\n[1/6] Country distribution")
    country_counter = extract_countries(merged, filter_tiers)
    print(f"  {len(country_counter)} countries, top: {country_counter.most_common(5)}")
    plot_country_treemap(country_counter, title)
    plot_country_pie(country_counter, title)
    plot_country_choropleth(country_counter, title)

    # 2. Institutions
    print("\n[2/6] Institution distribution")
    institutions = extract_institutions(merged, filter_tiers, top_n=200)
    print(f"  Top 3: {institutions[:3]}")
    plot_institution_treemap(institutions, title)
    plot_institution_pie(institutions, title)

    # 3. Word cloud
    print("\n[3/6] Keyword word cloud")
    kw_counter = extract_keywords(merged, filter_tiers)
    print(f"  {len(kw_counter)} unique keywords, top: {kw_counter.most_common(5)}")
    plot_wordcloud(kw_counter, title)

    # 4. Recommendation pie (only for full set)
    if not filter_tiers:
        print("\n[4/6] Recommendation distribution")
        plot_tier_pie(merged, title)

    # 5. Summary stats
    print("\n[5/6] Summary")
    tier_counter = Counter(m.get('recommendation_tier', 'Unknown') for m in merged)
    for tier, count in tier_counter.most_common():
        print(f"  {tier}: {count}")


def main():
    parser = argparse.ArgumentParser(description='Visualize conference paper data')
    parser.add_argument('--llm', required=True, help='LLM results JSON file')
    parser.add_argument('--papers', required=True, help='Crawled papers JSONL file')
    parser.add_argument('--name', default=None, help='Display name (default: from filename)')
    parser.add_argument('--filter-tiers', nargs='*', default=None,
                        help='Filter by recommendation tier (e.g. 深度解读 头条推荐)')
    parser.add_argument('--no-deep', action='store_true',
                        help='Skip generating deep analysis visualizations')
    args = parser.parse_args()

    # Determine display name
    if args.name:
        title = args.name
    else:
        basename = Path(args.llm).stem
        parts = basename.replace('LLM_results_', '')
        if 'iclr' in parts:
            title = f'ICLR {parts[-4:]}'
        elif 'icml' in parts:
            title = f'ICML {parts[-4:]}'
        else:
            title = parts.upper()

    print(f"\n{'='*60}")
    print(f"Visualizing: {title}")
    print(f"{'='*60}")

    # Load data
    print("Loading LLM results...")
    llm_results = load_llm_results(args.llm)
    print(f"  {len(llm_results)} results")

    print("Loading crawled papers...")
    papers = load_papers(args.papers)
    print(f"  {len(papers)} papers")

    # Match
    print("Matching...")
    merged = match_papers(llm_results, papers)
    matched_count = sum(1 for m in merged if m.get('_paper_data'))
    print(f"  {matched_count}/{len(merged)} matched")

    # Run full visualization
    filter_tiers = args.filter_tiers if args.filter_tiers else None
    run_visualization(merged, title, filter_tiers)

    # Also run deep analysis visualization (unless --no-deep or already filtered)
    if not args.no_deep and not filter_tiers:
        deep_tiers = ['深度解读', '头条推荐']
        run_visualization(merged, title, deep_tiers)

    print(f"\n{'='*60}")
    print(f"Done! Output in: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
