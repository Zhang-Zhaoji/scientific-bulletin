"""Stage or apply recovered abstracts, reassessments, reports, and source charts."""
import argparse
from collections import Counter
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from audit_bulletin_abstracts import ROOT, SELECTED, fingerprint, identity, normalized_title, substantive
from recover_bulletin_abstracts import atomic_json, verified


def stage(run):
    inventory = json.loads((run / 'inventory.json').read_text(encoding='utf-8'))
    revision_date = datetime.fromisoformat(inventory['created_at']).astimezone().date().isoformat()
    targets = {target['key']: target for target in json.loads((run / 'targets.json').read_text(encoding='utf-8'))}
    recovered = {row['key']: row for row in json.loads((run / 'recovery.json').read_text(encoding='utf-8')) if row['status'] == 'recovered'}
    evaluated = json.loads((run / 'reevaluated.json').read_text(encoding='utf-8'))
    if set(recovered) != set(evaluated):
        raise ValueError('Every recovered abstract must have a complete reevaluation')
    for key, record in recovered.items():
        if not substantive(record['abstract']) or evaluated[key]['paper']['abstract'] != record['abstract']:
            raise ValueError('Recovery and model inputs differ')
    sys.path.insert(0, str(ROOT / 'LLM_eval'))
    sys.path.insert(0, str(ROOT / 'visualize'))
    from Summary import ReportGenerator
    from generate_score_histograms import render_histogram, score_distribution
    from global_heatmap import WorldHeatmap

    manifest = {'created_at': datetime.now().isoformat(), 'files': [], 'issues': [],
                'unique_recovered': len(recovered), 'unique_reevaluated': len(evaluated), 'changes': []}
    occurrence_keys = {(occurrence['result'], occurrence['index']): target['key']
                       for target in targets.values() for occurrence in target['occurrences']}

    def save(target, text=None, source=None):
        relative = target.relative_to(ROOT)
        output = run / 'staged' / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if source:
            shutil.copy2(source, output)
        else:
            output.write_text(text, encoding='utf-8')
        manifest['files'].append({'target': str(relative), 'staged': str(output.relative_to(run)),
                                  'before_sha256': fingerprint(target) if target.exists() else None,
                                  'after_sha256': fingerprint(output)})

    for issue in inventory['issues']:
        result_path = ROOT / issue['result']
        if fingerprint(result_path) != issue['result_sha256']:
            raise ValueError('An inventoried result changed concurrently: ' + str(result_path))
        original = json.loads(result_path.read_text(encoding='utf-8'))
        results, changed = [], []
        for index, result in enumerate(original):
            key = occurrence_keys.get((issue['result'], index))
            if key not in recovered:
                kept = copy.deepcopy(result)
                if not substantive(kept['paper'].get('abstract')):
                    kept['input_quality_warning'] = 'Source abstract unavailable or insufficient; historical assessment is unverified.'
                results.append(kept)
                continue
            record = recovered[key]
            if not verified(result['paper']['raw_data'], targets[key]['paper']):
                raise ValueError('Conflicting identifiers across historical occurrences: ' + result['paper']['title'])
            replacement = copy.deepcopy(evaluated[key])
            paper = copy.deepcopy(result['paper'])
            raw = paper.setdefault('raw_data', {})
            for value in (paper, raw):
                value.update(abstract=record['abstract'], abstract_source=record['abstract_source'],
                             abstract_source_url=record.get('abstract_source_url'))
            replacement['paper'] = paper
            replacement.pop('input_quality_warning', None)
            replacement['abstract_recovery'] = {'run_date': revision_date, 'key': key,
                'previous_score': result.get('total_score'), 'previous_tier': result.get('recommendation_tier'),
                'previous_model': result.get('model_used'), 'source': record['abstract_source'],
                'source_url': record.get('abstract_source_url')}
            results.append(replacement)
            changed.append(key)
            manifest['changes'].append({'issue': issue['issue'], 'result': issue['result'],
                'key': key, 'title': paper['title'], 'before_score': result.get('total_score'),
                'after_score': replacement.get('total_score'), 'before_tier': result.get('recommendation_tier'),
                'after_tier': replacement.get('recommendation_tier')})
        if not changed:
            continue
        if len(results) != len(original) or any(before['paper']['title'] != after['paper']['title'] for before, after in zip(original, results)):
            raise ValueError('Result identity or ordering changed')
        save(result_path, json.dumps(results, ensure_ascii=False, indent=2) + '\n')
        by_title = {normalized_title(result['paper']['title']): result['paper']['raw_data'] for result in results}
        by_identity = {identity(result['paper']['raw_data']): result['paper']['raw_data'] for result in results}
        for suffix in ('_enriched_ror_refined', '_enriched', ''):
            path = ROOT / issue['source'].replace('_enriched_ror_refined', suffix)
            if not path.exists():
                continue
            rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
            for paper in rows:
                paired = by_identity.get(identity(paper))
                if paired and not substantive(paper.get('abstract')) and identity(paper) in recovered:
                    if identity(paper) != identity(paired) or not verified(paper, paired):
                        raise ValueError('Source layer identity mismatch: ' + paper['title'])
                    for field in ('abstract', 'abstract_source', 'abstract_source_url'):
                        paper[field] = paired.get(field)
            save(path, ''.join(json.dumps(paper, ensure_ascii=False) + '\n' for paper in rows))
        folder = run / 'report_build' / issue['date']
        folder.mkdir(parents=True, exist_ok=True)
        payload = folder / 'results.json'
        payload.write_text(json.dumps(results, ensure_ascii=False), encoding='utf-8')
        generated = ReportGenerator(str(folder)).generate_from_json(str(payload), source_statistics=True, render_histogram=False)
        if generated['statistics']['total'] != len(results) or not generated['statistics_text']:
            raise ValueError('Incomplete regenerated report statistics')
        report_path = ROOT / issue['report']
        old_markdown = report_path.read_text(encoding='utf-8')
        marker = '## 📊 本周概览\n\n'
        if marker not in old_markdown:
            raise ValueError('Historical overview marker missing: ' + issue['report'])
        fresh = Path(generated['markdown_path']).read_text(encoding='utf-8')
        selected = [result for result in results if result.get('recommendation_tier') in SELECTED]
        remaining = sum(not substantive(result['paper'].get('abstract')) for result in selected)
        dates = re.search(r'文献日期[：:]\s*(\d{4}-\d{2}-\d{2})[—–~至]+(\d{4}-\d{2}-\d{2})', old_markdown)
        date_note = '原报告文献日期范围：' + '—'.join(dates.groups()) + '。' if dates else ''
        note = (f'> 历史摘要修订（{revision_date}）：第 {issue["issue"]:03d} 期保留历史期号、日期与封面。'
                f'{date_note}本期 {len(results)} 条记录中补回 {len(changed)} 条正式摘要，'
                f'仅对这些条目使用 DeepSeek 重新评分和分级推荐，其余评估保持原值。'
                f'修订后拟发布 {len(selected)} 篇，其中 {remaining} 篇仍缺充分摘要，已保留资料不足提示。'
                f'来源、旧评分和推荐变更见 getfiles/abstract_history_{revision_date}.json。\n\n')
        markdown = old_markdown.split(marker, 1)[0] + marker + note + fresh.split(marker, 1)[1]
        entries = Counter(normalized_title(title) for title in re.findall(r'^### (.+)$', markdown, re.M)
                          if normalized_title(title) in by_title)
        expected = Counter(normalized_title(result['paper']['title']) for result in selected)
        if entries != expected:
            raise ValueError('Selected report entry counts differ: ' + issue['report'])
        save(report_path, markdown)
        histogram = folder / 'histogram.png'
        distribution = score_distribution(results)
        if sum(count for _, count in distribution) != sum(result.get('domain') != '域外局限' for result in results):
            raise ValueError('Histogram count differs')
        render_histogram(distribution, histogram)
        iso_date = datetime.strptime(issue['date'], '%Y%m%d').date().isoformat()
        save(ROOT / f'Imgs/visulize_img/statistics/{iso_date}_score_histogram.png', source=histogram)
        source_date = re.search(r'\d{4}-\d{2}-\d{2}', issue['source'])[0]
        for prefix in ('summary', 'quality'):
            audit_path = ROOT / f'getfiles/{prefix}_{source_date}.json'
            if audit_path.exists():
                weekly_audit = json.loads(audit_path.read_text(encoding='utf-8'))
                weekly_audit.update(abstract_history_revision=revision_date,
                    missing_abstracts=sum(not substantive(result['paper'].get('abstract')) for result in results),
                    selected_missing_abstracts=remaining,
                    recommendation_distribution=dict(Counter(result.get('recommendation_tier') for result in results)),
                    missing_abstract_count_after_enrichment=sum(not substantive(result['paper'].get('abstract')) for result in results))
                save(audit_path, json.dumps(weekly_audit, ensure_ascii=False, indent=2))
        cohort = [result['paper']['raw_data'] for result in results if result.get('domain') != '域外局限']
        geography = folder / 'geography.jsonl'
        geography.write_text(''.join(json.dumps(paper, ensure_ascii=False) + '\n' for paper in cohort), encoding='utf-8')
        chart = WorldHeatmap(None)
        chart.HEATMAP_ROOT_DIR = str(folder / 'globalHeatmap')
        chart.PIE_ROOT_DIR = str(folder / 'countryPie')
        Path(chart.HEATMAP_ROOT_DIR).mkdir(exist_ok=True)
        Path(chart.PIE_ROOT_DIR).mkdir(exist_ok=True)
        chart.skip_screenshots = True
        counts = chart.get_jsonl_country_data(str(geography))
        chart.metadata['source'] = issue['source'] + ' (excluding 域外局限)'
        chart.render_heatmap(counts, source_date)
        chart.render_pie_chart(counts, output_date=source_date)
        for subdir, filenames in [('globalHeatmap', [f'{source_date}_heatmap.html', f'{source_date}_heatmap.data.json']), ('countryPie', [f'{source_date}_pie.html'])]:
            for name in filenames:
                save(ROOT / 'Imgs/visulize_img' / subdir / name, source=folder / subdir / name)
        manifest['issues'].append(dict(issue, recovered_occurrences=len(changed),
            selected_after=len(selected), selected_missing_after=remaining,
            tiers_after=dict(Counter(result.get('recommendation_tier') for result in results))))
        print('STAGED', issue['date'], 'RECOVERED', len(changed), 'SELECTED', len(selected), 'MISSING', remaining, flush=True)
    atomic_json(run / 'apply_manifest.json', manifest)
    print('STAGED ISSUES', len(manifest['issues']), 'FILES', len(manifest['files']), flush=True)


def apply(run):
    manifest = json.loads((run / 'apply_manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        target = ROOT / entry['target']
        current = fingerprint(target) if target.exists() else None
        if current not in (entry['before_sha256'], entry['after_sha256']):
            raise ValueError('Concurrent modification before apply: ' + str(target))
        if fingerprint(run / entry['staged']) != entry['after_sha256']:
            raise ValueError('Staged file changed: ' + entry['staged'])
    for entry in manifest['files']:
        target = ROOT / entry['target']
        if entry['before_sha256'] is not None:
            backup = run / 'source_backups' / entry['target']
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                if fingerprint(target) != entry['before_sha256']:
                    raise ValueError('Original backup is missing for an already applied file')
                shutil.copy2(target, backup)
            if fingerprint(backup) != entry['before_sha256']:
                raise ValueError('Backup verification failed: ' + str(backup))
    for entry in manifest['files']:
        target = ROOT / entry['target']
        if target.exists() and fingerprint(target) == entry['after_sha256']:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.abstract-recovery.tmp')
        shutil.copy2(run / entry['staged'], temporary)
        temporary.replace(target)
    manifest['status'] = 'applied'
    atomic_json(run / 'apply_manifest.json', manifest)
    print('APPLIED', len(manifest['files']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    (apply if args.apply else stage)(args.run_dir.resolve())
