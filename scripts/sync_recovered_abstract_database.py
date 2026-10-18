"""Synchronize recovered abstracts and reassessed classifications with stable IDs."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

from audit_bulletin_abstracts import ROOT, canonical_doi, fingerprint, identity, substantive
from recover_bulletin_abstracts import atomic_json, verified
from update_bulletin_database import backup_database, snapshot
from finalize_bulletin_report import publication_date

sys.path.insert(0, str(ROOT))
from sql_scripts.build_slim_db import build_slim_db, verify_slim_db
from sql_scripts.build_sqlite import parse_work_details

CLASSIFICATIONS = [('themes', 'article_themes', 'theme_id'),
                   ('subthemes', 'article_subthemes', 'subtheme_id'),
                   ('crosstags', 'article_crosstags', 'tag_id')]


def projection(candidates, stored):
    matching = [row for row in candidates if verified(stored, row['paper']['raw_data'])]
    if not matching:
        raise ValueError('No identity-verified database projection: ' + stored['title'])
    return max(matching, key=lambda row: (
        row['paper']['raw_data']['title'] == stored['title'],
        publication_date(row['paper']['raw_data'].get('date')) == publication_date(stored.get('pub_date')),
        row['_issue_date']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    manifest = json.loads((run / 'apply_manifest.json').read_text(encoding='utf-8'))
    recovered = {row['key'] for row in json.loads((run / 'recovery.json').read_text(encoding='utf-8')) if row['status'] == 'recovered'}
    inventory = json.loads((run / 'inventory.json').read_text(encoding='utf-8'))
    full = ROOT / 'data/literature.db'
    slim = ROOT / 'docs/assets/data/literature_slim.db'
    fingerprints = [fingerprint(full), fingerprint(slim)]
    backup_dir = run / 'database_backup'
    backup_dir.mkdir(exist_ok=True)
    token = datetime.now().strftime('%Y%m%d_%H%M%S')
    full_backup = backup_dir / ('literature_' + token + '.db')
    slim_backup = backup_dir / ('literature_slim_' + token + '.db')
    backup_database(full, full_backup)
    backup_database(slim, slim_backup)
    staged_full, staged_slim = run / 'literature_staged.db', run / 'literature_slim_staged.db'
    backup_database(full_backup, staged_full)
    with closing(sqlite3.connect(staged_full)) as connection:
        connection.row_factory = sqlite3.Row
        original = {row['id']: dict(row) for row in connection.execute('SELECT * FROM articles')}
        old_ids = set(original)
        by_doi, by_pmid, by_title = {}, {}, {}
        for identifier, row in original.items():
            if row.get('doi'):
                by_doi.setdefault(canonical_doi(row['doi']), set()).add(identifier)
            if row.get('pmid'):
                by_pmid.setdefault(str(row['pmid']), set()).add(identifier)
            by_title.setdefault(row['title'], set()).add(identifier)
        candidates, affected, unresolved, repeated_ids = {}, set(), [], {}
        for issue in inventory['issues']:
            staged = run / 'staged' / issue['result']
            rows = json.loads((staged if staged.exists() else ROOT / issue['result']).read_text(encoding='utf-8'))
            for result in rows:
                paper = result['paper']['raw_data']
                identifiers = by_title.get(paper['title'], set()) | by_doi.get(canonical_doi(paper.get('doi')), set()) | by_pmid.get(str(paper.get('pmid') or ''), set())
                identifiers = {identifier for identifier in identifiers if verified(original[identifier], paper)}
                if not identifiers:
                    if identity(paper) in recovered:
                        unresolved.append({'title': paper['title'], 'key': identity(paper), 'matches': sorted(identifiers)})
                    continue
                result['_issue_date'] = issue['date']
                for identifier in identifiers:
                    candidates.setdefault(identifier, []).append(result)
                    if result.get('abstract_recovery', {}).get('key') in recovered:
                        affected.add(identifier)
                        if len(identifiers) > 1:
                            repeated_ids[identity(paper)] = sorted(identifiers)
        if unresolved:
            atomic_json(run / 'database_unresolved.json', unresolved)
            raise ValueError(f'{len(unresolved)} recovered occurrences lack a unique database identity; originals unchanged')
        before_links = {link: set(tuple(row) for row in connection.execute(f'SELECT article_id,{column} FROM {link}')) for _, link, column in CLASSIFICATIONS}
        changes = []
        for identifier in sorted(affected):
            row = original[identifier]
            result = projection(candidates[identifier], row)
            paper = result['paper']['raw_data']
            abstract = row.get('abstract')
            if not substantive(abstract) and substantive(paper.get('abstract')):
                abstract = paper['abstract']
            connection.execute('UPDATE articles SET abstract=?,score=?,title_zh=? WHERE id=?',
                               (abstract, result['total_score'], result.get('title_zh'), identifier))
            _, _, _, _, themes, subthemes, tags = parse_work_details(paper, result)
            expected = {}
            for (entity, link, column), values in zip(CLASSIFICATIONS, (themes, subthemes, tags)):
                connection.execute(f'DELETE FROM {link} WHERE article_id=?', (identifier,))
                names = sorted({value['name'] for value in values if value.get('name')})
                for name in names:
                    connection.execute(f'INSERT OR IGNORE INTO {entity}(name) VALUES (?)', (name,))
                    entity_id = connection.execute(f'SELECT id FROM {entity} WHERE name=?', (name,)).fetchone()[0]
                    connection.execute(f'INSERT OR IGNORE INTO {link}(article_id,{column}) VALUES (?,?)', (identifier, entity_id))
                actual = {record[0] for record in connection.execute(f'SELECT entity.name FROM {link} linked JOIN {entity} entity ON entity.id=linked.{column} WHERE linked.article_id=?', (identifier,))}
                if actual != set(names):
                    raise ValueError('Database classification reconciliation failed')
                expected[entity] = names
            changes.append({'article_id': identifier, 'title': row['title'], 'doi': row.get('doi'),
                'projection_issue': result['_issue_date'], 'preserved_pub_date': row['pub_date'],
                'before_score': row.get('score'), 'after_score': result['total_score'],
                'abstract_filled': not substantive(row.get('abstract')) and substantive(abstract),
                'classifications': expected})
        after = {row['id']: dict(row) for row in connection.execute('SELECT * FROM articles')}
        if set(after) != old_ids:
            raise ValueError('Article IDs changed')
        for identifier, old in original.items():
            allowed = {'abstract', 'score', 'title_zh'} if identifier in affected else set()
            if any(value != after[identifier][column] for column, value in old.items() if column not in allowed):
                raise ValueError('Unrequested article change: ' + str(identifier))
        for _, link, column in CLASSIFICATIONS:
            current = set(tuple(row) for row in connection.execute(f'SELECT article_id,{column} FROM {link}'))
            if {pair for pair in current if pair[0] not in affected} != {pair for pair in before_links[link] if pair[0] not in affected}:
                raise ValueError('Unselected classification links changed')
        connection.commit()
        connection.row_factory = None
        checked = snapshot(connection)
    build_slim_db(staged_full, staged_slim)
    if not verify_slim_db(staged_full, staged_slim):
        raise ValueError('Slim database verification failed')
    if [fingerprint(full), fingerprint(slim)] != fingerprints:
        raise ValueError('Database changed concurrently; staged databases retained')
    for source, target in [(staged_full, full), (staged_slim, slim)]:
        try:
            source.replace(target)
        except PermissionError:
            backup_database(source, target)
    with closing(sqlite3.connect(full)) as connection:
        final = snapshot(connection)
    if final != checked:
        raise ValueError('Published database differs from staged database')
    audit = {'status': 'complete', 'article_count': len(original), 'updated_articles': len(affected),
             'abstracts_filled': sum(change['abstract_filled'] for change in changes),
             'score_changes': sum(change['before_score'] != change['after_score'] for change in changes),
             'article_ids_and_dates_preserved': True, 'unselected_records_preserved': True,
             'integrity_check': 'ok', 'foreign_key_errors': 0,
             'projection_rule': 'Same identifiers and compatible title; prefer exact stored title, stored publication date, then latest issue. Preserve and synchronize existing duplicate article IDs without merging.',
             'existing_duplicate_id_groups': repeated_ids,
             'backups': [str(full_backup), str(slim_backup)], 'changes': changes}
    atomic_json(run / 'database_sync.json', audit)
    print(json.dumps({key: value for key, value in audit.items() if key != 'changes'}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
