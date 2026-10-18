"""Validate the complete historical abstract repair and write its formal audit."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from audit_bulletin_abstracts import ROOT, SELECTED, fingerprint, identity, normalized_title, substantive
from recover_bulletin_abstracts import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    inventory = json.loads((run / 'inventory.json').read_text(encoding='utf-8'))
    manifest = json.loads((run / 'apply_manifest.json').read_text(encoding='utf-8'))
    recovery = json.loads((run / 'recovery.json').read_text(encoding='utf-8'))
    evaluated = json.loads((run / 'reevaluated.json').read_text(encoding='utf-8'))
    database = json.loads((run / 'database_sync.json').read_text(encoding='utf-8'))
    recovered = {record['key']: record for record in recovery if record['status'] == 'recovered'}
    if set(evaluated) != set(recovered) or len(recovery) != inventory['unique_missing']:
        raise ValueError('Recovery attempts or reevaluations are incomplete')
    for entry in manifest['files']:
        if fingerprint(ROOT / entry['target']) != entry['after_sha256']:
            raise ValueError('Applied file differs from stage: ' + entry['target'])
        if entry['before_sha256'] and fingerprint(run / 'source_backups' / entry['target']) != entry['before_sha256']:
            raise ValueError('Original backup differs: ' + entry['target'])
    missing_keys, selected_missing_keys, issues, restored_keys = set(), set(), [], set()
    remaining_records = {}
    for issue in inventory['issues']:
        path = ROOT / issue['result']
        results = json.loads(path.read_text(encoding='utf-8'))
        if len(results) != issue['papers']:
            raise ValueError('Issue record count changed')
        source = {identity(json.loads(line)): json.loads(line) for line in (ROOT / issue['source']).read_text(encoding='utf-8').splitlines() if line.strip()}
        selected = [result for result in results if result.get('recommendation_tier') in SELECTED]
        missing = [result for result in results if not substantive(result['paper'].get('abstract'))]
        selected_missing = [result for result in missing if result.get('recommendation_tier') in SELECTED]
        for result in results:
            paper = result['paper']['raw_data']
            if identity(paper) not in source:
                raise ValueError('Result/source identity mismatch')
            if result.get('abstract_recovery'):
                key = result['abstract_recovery']['key']
                if not substantive(paper.get('abstract')) or paper['abstract'] != recovered[key]['abstract']:
                    raise ValueError('Applied abstract differs from source')
                if result['paper']['abstract'] != source[identity(paper)].get('abstract') or result['total_score'] != evaluated[key]['total_score']:
                    raise ValueError('Source/model result reconciliation failed')
                restored_keys.add(key)
            if not substantive(result['paper'].get('abstract')):
                missing_keys.add(identity(paper))
                remaining = remaining_records.setdefault(identity(paper), {
                    'key': identity(paper), 'title': paper['title'], 'doi': paper.get('doi'),
                    'pmid': paper.get('pmid'), 'source': paper.get('source'),
                    'selected': False, 'occurrences': []})
                remaining['selected'] |= result.get('recommendation_tier') in SELECTED
                remaining['occurrences'].append({'issue': issue['issue'], 'date': issue['date'],
                                                 'tier': result.get('recommendation_tier'), 'report': issue['report']})
                if result.get('recommendation_tier') in SELECTED:
                    selected_missing_keys.add(identity(paper))
        backup = run / 'source_backups' / issue['result']
        if backup.exists():
            original = json.loads(backup.read_text(encoding='utf-8'))
            for before, after in zip(original, results):
                if before['paper']['title'] != after['paper']['title'] or before['paper'].get('date') != after['paper'].get('date'):
                    raise ValueError('Historical paper title/date changed')
                if not after.get('abstract_recovery'):
                    allowed = {'input_quality_warning'}
                    if {key: value for key, value in before.items() if key not in allowed} != {key: value for key, value in after.items() if key not in allowed}:
                        raise ValueError('Unrepaired assessment changed')
        report = (ROOT / issue['report']).read_text(encoding='utf-8')
        titles = {normalized_title(result['paper']['title']) for result in results}
        actual = Counter(normalized_title(title) for title in re.findall(r'^### (.+)$', report, re.M) if normalized_title(title) in titles)
        expected = Counter(normalized_title(result['paper']['title']) for result in selected)
        if actual != expected:
            raise ValueError('Report selection count mismatch: ' + issue['report'])
        html_path = ROOT / 'docs' / (Path(issue['report']).stem + '.html')
        html = html_path.read_text(encoding='utf-8')
        references = re.findall(r'(?:src|href)=[\"\x27]([^\"\x27]+)[\"\x27]', html)
        for reference in references:
            if not re.match(r'^(?:https?:|data:|#|mailto:|javascript:)', reference) and not (html_path.parent / reference.split('#')[0].split('?')[0]).exists():
                raise ValueError('Broken local report reference: ' + reference)
        issues.append({'issue': issue['issue'], 'date': issue['date'], 'report': issue['report'],
            'papers': len(results), 'missing_before': issue['missing'], 'missing_after': len(missing),
            'selected_missing_before': issue['selected_missing'], 'selected_missing_after': len(selected_missing),
            'selected_before': issue['selected'], 'selected_after': len(selected)})
    if restored_keys != set(recovered):
        raise ValueError('Recovered unique papers and applied papers differ')
    for relative in ['data/literature.db', 'docs/assets/data/literature_slim.db']:
        with closing(sqlite3.connect((ROOT / relative).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Database integrity verification failed')
            if connection.execute('SELECT count(*) FROM articles').fetchone()[0] != database['article_count']:
                raise ValueError('Database article count changed')
    changes = manifest['changes']
    audit = {'status': 'passed', 'verified_at': datetime.now().isoformat(),
        'issues_checked': len(issues), 'issues_revised': len(manifest['issues']),
        'missing_occurrences_before': inventory['missing_occurrences'],
        'missing_occurrences_after': sum(issue['missing_after'] for issue in issues),
        'unique_missing_before': inventory['unique_missing'], 'unique_missing_after': len(missing_keys),
        'selected_missing_occurrences_before': inventory['selected_missing_occurrences'],
        'selected_missing_occurrences_after': sum(issue['selected_missing_after'] for issue in issues),
        'unique_selected_missing_before': inventory['unique_selected_missing'], 'unique_selected_missing_after': len(selected_missing_keys),
        'unique_abstracts_recovered_and_reevaluated': len(recovered),
        'restored_occurrences': len(changes), 'recommendation_changes': sum(change['before_tier'] != change['after_tier'] for change in changes),
        'tier_transitions': dict(Counter(change['before_tier'] + ' -> ' + change['after_tier'] for change in changes)),
        'database': {key: value for key, value in database.items() if key != 'changes'},
        'issues': issues, 'changes': changes,
        'recovery_evidence': [{key: value for key, value in record.items() if key != 'abstract'} |
                              ({'abstract_length': len(record['abstract']), 'abstract_sha256': hashlib.sha256(record['abstract'].encode()).hexdigest()} if record.get('abstract') else {}) for record in recovery]}
    revision_date = manifest['created_at'][:10]
    atomic_json(ROOT / f'getfiles/abstract_history_{revision_date}.json', audit)
    evidence = {record['key']: record for record in recovery}
    for key, remaining in remaining_records.items():
        remaining['retrieval'] = evidence[key]
    atomic_json(ROOT / f'getfiles/abstract_missing_{revision_date}.json', {
        'date': revision_date, 'unique_missing': len(remaining_records),
        'unique_selected_missing': len(selected_missing_keys),
        'papers': sorted(remaining_records.values(), key=lambda record: (not record['selected'], record['key']))})
    print(json.dumps({key: value for key, value in audit.items() if key not in {'issues', 'changes', 'recovery_evidence', 'tier_transitions'}}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
