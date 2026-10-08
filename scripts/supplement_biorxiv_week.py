"""Fetch a complete exact-date bioRxiv category interval with resumable page audits.

HTTP or API failures are errors, not an empty final page. Numeric cursor offsets
continue until the API's declared total is retrieved; no artificial record cap.
"""
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from crawler_biorxiv import parse_biorxiv_paper


def json_write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def jsonl_write(path, papers):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        for paper in papers:
            stream.write(json.dumps(paper, ensure_ascii=False) + '\n')
    temporary.replace(path)


def retrieve_page(start, end, category, cursor, cache, retries, audit):
    checkpoint = cache / f'page_{cursor:05d}.json'
    if checkpoint.exists():
        data = json.loads(checkpoint.read_text(encoding='utf-8'))
        return data, 'cache'
    url = f'https://api.biorxiv.org/details/biorxiv/{start}/{end}/{cursor}'
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params={'category': category, 'format': 'json', 'limit': 100}, timeout=40)
            response.raise_for_status()
            data = response.json()
            messages = data.get('messages', [])
            if not messages or messages[0].get('status') != 'ok':
                raise ValueError('API did not return status=ok')
            declared = int(messages[0]['total'])
            actual_cursor = int(messages[0].get('cursor', cursor))
            if actual_cursor != cursor:
                raise ValueError(f'API cursor {actual_cursor} does not match requested {cursor}')
            if not data.get('collection') and cursor < declared:
                raise ValueError('Empty collection before declared total')
            json_write(checkpoint, data)
            return data, response.url
        except (requests.RequestException, ValueError, KeyError) as exc:
            audit['retries'].append({'cursor': cursor, 'attempt': attempt, 'error': str(exc)})
            print(f'bioRxiv cursor={cursor} attempt={attempt}: {type(exc).__name__}', flush=True)
            if attempt == retries:
                raise RuntimeError(f'bioRxiv page cursor={cursor} failed after {retries} attempts') from exc
            time.sleep(min(2 ** (attempt - 1), 16))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--end-date', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--category', default='neuroscience')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--retries', type=int, default=6)
    parser.add_argument('--no-append', action='store_true')
    args = parser.parse_args()
    if args.end_date < args.start_date:
        parser.error('end-date precedes start-date')
    output = args.output_dir or ROOT / f'tmps/pipeline_{args.end_date:%Y%m%d}'
    output.mkdir(parents=True, exist_ok=True)
    cache = output / f'biorxiv_pages_{args.start_date}_{args.end_date}_{args.category}'
    cache.mkdir(exist_ok=True)
    audit_path = output / 'biorxiv_supplement_audit.json'
    audit = {'date_range': [str(args.start_date), str(args.end_date)], 'category': args.category,
             'status': 'running', 'pages': [], 'retries': [], 'retrieved_records': 0,
             'date_semantics': 'bioRxiv API record date is the posted version date; revisions may be included.'}
    raw, cursor, total, signatures = [], 0, None, set()
    try:
        while total is None or cursor < total:
            data, evidence_url = retrieve_page(args.start_date, args.end_date, args.category, cursor, cache, args.retries, audit)
            message = data['messages'][0]
            declared = int(message['total'])
            if total is not None and declared != total:
                raise RuntimeError(f'bioRxiv total changed from {total} to {declared}; snapshot needs recheck')
            total = declared
            records = data.get('collection', [])
            signature = tuple((p.get('doi'), p.get('version'), p.get('date')) for p in records)
            if signature and signature in signatures:
                raise RuntimeError('Repeated page records despite changing cursor')
            signatures.add(signature)
            audit['pages'].append({'cursor': cursor, 'count': len(records), 'declared_total': total,
                                    'count_new_papers': message.get('count_new_papers'), 'evidence_url': evidence_url})
            raw.extend(records)
            cursor += len(records)
            audit['retrieved_records'] = len(raw)
            audit['declared_total'] = total
            json_write(audit_path, audit)
            print(f'bioRxiv exact week: {cursor}/{total}', flush=True)
            if not records:
                if cursor < total:
                    raise RuntimeError('Unexpected empty page')
                break
            time.sleep(0.25)
        if len(raw) != total:
            raise RuntimeError(f'Pagination incomplete: {len(raw)}/{total}')
        unique, rejected = {}, Counter()
        for item in raw:
            try:
                date = dt.date.fromisoformat(item.get('date', ''))
            except ValueError:
                rejected['unknown_date'] += 1
                continue
            if not args.start_date <= date <= args.end_date:
                rejected['outside_window'] += 1
                continue
            if item.get('category') != args.category:
                rejected['other_category'] += 1
                continue
            key = item.get('doi')
            if not key:
                rejected['missing_doi'] += 1
                continue
            version = int(item.get('version', 0))
            if key in unique and int(unique[key].get('version', 0)) >= version:
                continue
            unique[key] = item
        papers = []
        for item in unique.values():
            paper = parse_biorxiv_paper(item)
            if not paper:
                raise RuntimeError('Unable to parse accepted bioRxiv source record')
            paper['date'] = item['date']
            paper['version'] = item.get('version')
            paper['date_evidence'] = {'field': 'bioRxiv API record date', 'value': item['date'],
                                      'version': item.get('version'), 'interval': audit['date_range']}
            paper['abstract_source'] = 'bioRxiv details API'
            paper['retrieval_source'] = 'bioRxiv complete date-bounded details API'
            papers.append(paper)
        papers.sort(key=lambda p: (p['date'], p['doi']))
        jsonl_write(output / 'biorxiv_supplement.jsonl', papers)
        audit.update(status='complete', complete_pagination=True, unique_papers=len(papers),
                     deduplicated_version_records=len(raw) - len(unique), rejected=dict(rejected),
                     missing_abstract_count=sum(not p.get('abstract') for p in papers),
                     finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
        json_write(audit_path, audit)
        combined_path = output / 'supplement.jsonl'
        if combined_path.exists() and not args.no_append:
            existing = [json.loads(line) for line in combined_path.read_text(encoding='utf-8').splitlines() if line.strip()]
            existing = [p for p in existing if p.get('source') != 'bioRxiv']
            combined = sorted(existing + papers, key=lambda p: (p['date'], p['source'], p['title']))
            jsonl_write(combined_path, combined)
            combined_audit = output / 'supplement_audit.json'
            if combined_audit.exists():
                previous = json.loads(combined_audit.read_text(encoding='utf-8'))
                previous.update(count=len(combined), counts=dict(Counter(p['source'] for p in combined)),
                                missing_abstract_count=sum(not p.get('abstract') for p in combined),
                                biorxiv_pagination=audit)
                json_write(combined_audit, previous)
        print(json.dumps({k: audit[k] for k in ('status', 'retrieved_records', 'declared_total', 'unique_papers', 'missing_abstract_count')}), flush=True)
    except Exception as exc:
        audit.update(status='failed', error=str(exc), complete_pagination=False)
        json_write(audit_path, audit)
        raise


if __name__ == '__main__':
    main()
