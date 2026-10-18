"""Inventory missing abstracts in regular issues, retaining issue and paper identity."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import argparse

ROOT = Path(__file__).resolve().parents[1]
SELECTED = {'头条推荐', '深度解读', '简要提及', '域外高影响'}
EXCLUDED_NAMES = ('wechat', 'specialissue', '.raw', '.deprecated')


def normalized_title(value):
    return re.sub(r'\W+', '', str(value or '').casefold())


def canonical_doi(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', str(value or '').strip(), flags=re.I).lower()


def substantive(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if len(text) < 50:
        return False
    lowered = text.casefold()
    return not any(lowered.startswith(prefix) for prefix in (
        'this scientific commentary refers to', 'this is a correction to',
        'no abstract available', 'abstract not available', 'abstract unavailable',
    ))


def identity(paper):
    doi = canonical_doi(paper.get('doi'))
    source = str(paper.get('source') or paper.get('journal') or '').lower()
    version = str(paper.get('version') or '') if any(name in source for name in ('biorxiv', 'arxiv')) else ''
    if doi:
        return 'doi:' + doi + (':version:' + version if version else '')
    if paper.get('pmid'):
        return 'pmid:' + str(paper['pmid']).strip()
    return 'title:' + normalized_title(paper.get('title'))


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(run):
    run.mkdir(parents=True, exist_ok=True)
    report_paths = sorted(path for path in (ROOT / 'LLM_Results').glob('report_*.md')
                          if not any(word in path.name for word in EXCLUDED_NAMES))
    report_titles = {path: {normalized_title(title) for title in re.findall(
        r'^### (.+)$', path.read_text(encoding='utf-8'), re.M)} for path in report_paths}
    source_paths = sorted((ROOT / 'getfiles').glob('all_papers_*_enriched_ror_refined.jsonl'))
    source_titles = {path: {normalized_title(json.loads(line)['title']) for line in path.read_text(
        encoding='utf-8').splitlines() if line.strip()} for path in source_paths}
    issues, targets, used_reports, used_sources = [], {}, set(), set()
    result_paths = sorted(path for path in (ROOT / 'LLM_Results').glob('LLM_results_20*.json')
                          if re.match(r'LLM_results_\d{8}(?:_|\.)', path.name)
                          and not any(word in path.name for word in EXCLUDED_NAMES))
    for result_path in result_paths:
        rows = json.loads(result_path.read_text(encoding='utf-8'))
        titles = {normalized_title(row['paper']['title']) for row in rows}
        source = max(source_paths, key=lambda path: len(titles & source_titles[path]) / max(len(titles), len(source_titles[path])))
        if not titles.issubset(source_titles[source]) or source in used_sources:
            raise ValueError('No uniquely aligned source corpus: ' + result_path.name)
        report = max(report_paths, key=lambda path: len(titles & report_titles[path]))
        if not titles.intersection(report_titles[report]) or report in used_reports:
            raise ValueError('No uniquely aligned report: ' + result_path.name)
        used_sources.add(source)
        used_reports.add(report)
        missing_rows = [row for row in rows if not substantive(row['paper'].get('abstract'))]
        issue_date = re.search(r'\d{8}', report.name)[0]
        issue = {'issue': report_paths.index(report) + 1, 'date': issue_date,
                 'result': str(result_path.relative_to(ROOT)), 'source': str(source.relative_to(ROOT)),
                 'report': str(report.relative_to(ROOT)), 'result_sha256': fingerprint(result_path),
                 'papers': len(rows), 'selected': sum(row.get('recommendation_tier') in SELECTED for row in rows),
                 'missing': len(missing_rows), 'selected_missing': sum(row.get('recommendation_tier') in SELECTED for row in missing_rows),
                 'missing_by_tier': dict(Counter(row.get('recommendation_tier') for row in missing_rows))}
        issues.append(issue)
        for index, row in enumerate(rows):
            if substantive(row['paper'].get('abstract')):
                continue
            paper = dict(row['paper'].get('raw_data') or {})
            paper.setdefault('title', row['paper']['title'])
            paper.setdefault('abstract', row['paper'].get('abstract') or '')
            key = identity(paper)
            target = targets.setdefault(key, {'key': key, 'paper': paper, 'occurrences': [], 'selected': False})
            target['selected'] |= row.get('recommendation_tier') in SELECTED
            target['occurrences'].append({'result': issue['result'], 'index': index,
                                          'title': row['paper']['title'], 'tier': row.get('recommendation_tier'),
                                          'issue': issue['issue'], 'date': issue_date})
    targets = sorted(targets.values(), key=lambda target: (not target['selected'], target['key']))
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'issues': issues,
                'issue_count': len(issues), 'papers': sum(issue['papers'] for issue in issues),
                'missing_occurrences': sum(issue['missing'] for issue in issues),
                'selected_missing_occurrences': sum(issue['selected_missing'] for issue in issues),
                'unique_missing': len(targets), 'unique_selected_missing': sum(target['selected'] for target in targets),
                'sources_of_selected_missing': dict(Counter(target['paper'].get('source', 'unknown') for target in targets if target['selected']))}
    (run / 'inventory.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (run / 'targets.json').write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in manifest.items() if key != 'issues'}, ensure_ascii=False, indent=2), flush=True)
    return manifest, targets


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    audit(args.run_dir)
