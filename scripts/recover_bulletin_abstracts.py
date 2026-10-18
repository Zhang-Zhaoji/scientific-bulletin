"""Recover identity-verified historical abstracts into resumable staging files."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz

from audit_bulletin_abstracts import ROOT, canonical_doi, normalized_title, substantive

sys.path.insert(0, str(ROOT / 'src'))
from enrich_source_metadata import parse_pubmed_root


def verified(paper, record):
    expected, actual = canonical_doi(paper.get('doi')), canonical_doi(record.get('doi'))
    if expected and actual and expected != actual:
        return False
    expected_pmid = str(paper.get('pmid') or '').strip()
    actual_pmid = str(record.get('pmid') or '').strip()
    if expected_pmid and actual_pmid and expected_pmid != actual_pmid:
        return False
    matching_id = bool(expected and expected == actual) or bool(
        paper.get('pmid') and str(paper['pmid']) == str(record.get('pmid') or ''))
    return matching_id and fuzz.ratio(normalized_title(paper['title']), normalized_title(record.get('title'))) >= 95


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def read_pubmed(path):
    root = ET.fromstring(path.read_bytes())
    rows = parse_pubmed_root(root)
    for pmid, record in rows.items():
        record.update(pmid=pmid, abstract_source='PubMed XML',
                      abstract_source_url='https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/',
                      evidence_file=str(path.relative_to(ROOT)))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    run = args.run_dir.resolve()
    targets = json.loads((run / 'targets.json').read_text(encoding='utf-8'))
    cache = run / 'retrieval_cache'
    cache.mkdir(exist_ok=True)
    records, by_doi = {}, {}
    paths = set((ROOT / 'tmps').glob('**/source_cache/pubmed_*.xml'))
    paths.update(cache.glob('pubmed_*.xml'))
    for path in sorted(paths):
        try:
            for pmid, record in read_pubmed(path).items():
                if substantive(record.get('abstract')) or pmid not in records:
                    records[pmid] = record
                doi = canonical_doi(record.get('doi'))
                if doi and (substantive(record.get('abstract')) or doi not in by_doi):
                    by_doi[doi] = record
        except (ET.ParseError, OSError) as error:
            print('Invalid cache', path, str(error), flush=True)
    doi_cache = ROOT / 'tmps/affiliation_history_20261008/doi_records.json'
    if doi_cache.exists():
        for doi, candidates in json.loads(doi_cache.read_text(encoding='utf-8')).items():
            for candidate in candidates:
                abstract = BeautifulSoup(candidate.get('abstractText') or '', 'html.parser').get_text(' ', strip=True)
                if substantive(abstract):
                    by_doi[canonical_doi(doi)] = dict(candidate, abstract=abstract,
                        abstract_source='Cached Europe PMC core',
                        abstract_source_url='https://europepmc.org/article/' + candidate.get('source', 'MED') + '/' + str(candidate.get('id', '')),
                        evidence_file=str(doi_cache.relative_to(ROOT)))
    outcomes = {}
    outcome_path = run / 'recovery.json'
    if outcome_path.exists():
        outcomes.update({record['key']: record for record in json.loads(outcome_path.read_text(encoding='utf-8'))})

    def accept(target):
        paper = target['paper']
        candidates = [records.get(str(paper.get('pmid') or '')), by_doi.get(canonical_doi(paper.get('doi')))]
        if substantive(paper.get('abstract')):
            candidates.insert(0, dict(paper, abstract_source='Previously stored source metadata', abstract_source_url=paper.get('url')))
        for record in candidates:
            if record and verified(paper, record) and substantive(record.get('abstract')):
                return {'key': target['key'], 'status': 'recovered', 'title': paper['title'],
                        'abstract': record['abstract'], 'abstract_source': record.get('abstract_source', 'PubMed XML'),
                        'abstract_source_url': record.get('abstract_source_url'), 'evidence_file': record.get('evidence_file'),
                        'doi': canonical_doi(record.get('doi')), 'pmid': record.get('pmid')}
        return None

    for target in targets:
        record = accept(target)
        if record:
            outcomes[target['key']] = record
    print('LOCAL', Counter(record['status'] for record in outcomes.values()), 'TARGETS', len(targets), flush=True)
    atomic_json(outcome_path, list(outcomes.values()))
    if args.fetch:
        missing_ids = sorted({str(target['paper']['pmid']) for target in targets
                              if target['key'] not in outcomes and target['paper'].get('pmid')})
        for offset in range(0, len(missing_ids), 100):
            batch = missing_ids[offset:offset + 100]
            digest = hashlib.sha256(','.join(batch).encode()).hexdigest()[:16]
            path = cache / ('pubmed_' + digest + '.xml')
            for attempt in range(4):
                try:
                    response = requests.get('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi', params={'db': 'pubmed', 'id': ','.join(batch), 'retmode': 'xml'}, timeout=50)
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                    if root.find('ERROR') is not None:
                        raise ValueError('PubMed XML error')
                    path.write_bytes(response.content)
                    records.update(read_pubmed(path))
                    break
                except (requests.RequestException, ValueError) as error:
                    print('PubMed batch retry', offset, attempt, str(error), flush=True)
                    time.sleep(2 * (attempt + 1))
            time.sleep(.5)
        for record in records.values():
            doi = canonical_doi(record.get('doi'))
            if doi and substantive(record.get('abstract')):
                by_doi[doi] = record
        for target in targets:
            record = accept(target)
            if record:
                outcomes[target['key']] = record
        atomic_json(outcome_path, list(outcomes.values()))
        pending = [target for target in targets if target['key'] not in outcomes]

        def retrieve(target):
            paper = target['paper']
            doi = canonical_doi(paper.get('doi'))
            record = {'key': target['key'], 'title': paper['title'], 'status': 'not_recovered', 'attempts': []}
            if not doi:
                record['reason'] = 'No verified DOI; no title-only abstract transfer'
                return record
            digest = hashlib.sha256(target['key'].encode()).hexdigest()[:20]
            for source, url, params in [('Europe PMC', 'https://www.ebi.ac.uk/europepmc/webservices/rest/search', {'query': 'DOI:"' + doi + '"', 'format': 'json', 'resultType': 'core'}), ('Crossref', 'https://api.crossref.org/works/' + doi, None), ('publisher', 'https://doi.org/' + doi, None)]:
                path = cache / (digest + '_' + source.replace(' ', '_'))
                try:
                    if path.exists():
                        content = path.read_text(encoding='utf-8')
                        evidence_url = json.loads(path.with_suffix('.request.json').read_text(encoding='utf-8'))['url']
                    else:
                        response = requests.get(url, params=params, headers={'User-Agent': 'NeuroscienceBulletin/1.0 (source metadata recovery)'}, timeout=25)
                        record['attempts'].append({'source': source, 'url': response.url, 'http_status': response.status_code})
                        response.raise_for_status()
                        response.encoding = 'utf-8'
                        content, evidence_url = response.text, response.url
                        path.write_text(content, encoding='utf-8')
                        atomic_json(path.with_suffix('.request.json'), {'url': evidence_url, 'status': response.status_code})
                    candidates = []
                    if source == 'Europe PMC':
                        candidates = [{'doi': item.get('doi'), 'pmid': item.get('pmid'), 'title': item.get('title'), 'abstract': BeautifulSoup(item.get('abstractText') or '', 'html.parser').get_text(' ', strip=True)} for item in json.loads(content).get('resultList', {}).get('result', [])]
                    elif source == 'Crossref':
                        item = json.loads(content)['message']
                        candidates = [{'doi': item.get('DOI'), 'title': (item.get('title') or [''])[0], 'abstract': BeautifulSoup(item.get('abstract') or '', 'html.parser').get_text(' ', strip=True)}]
                    else:
                        soup = BeautifulSoup(content, 'html.parser')
                        meta = lambda name: soup.find('meta', attrs={'name': name})
                        doi_tag, title_tag = meta('citation_doi'), meta('citation_title')
                        candidates = [{'doi': doi_tag.get('content') if doi_tag else '', 'title': title_tag.get('content') if title_tag else '', 'abstract': '\n'.join(node.get_text(' ', strip=True) for node in soup.select('#abstract, .abstract, #Abs1-content, section.abstract'))}]
                    for candidate in candidates:
                        if verified(paper, candidate) and substantive(candidate.get('abstract')):
                            record.update(status='recovered', abstract=candidate['abstract'], abstract_source=source + ' DOI/title-verified', abstract_source_url=evidence_url, evidence_file=str(path.relative_to(ROOT)))
                            return record
                except (requests.RequestException, ValueError, KeyError, OSError) as error:
                    record['attempts'].append({'source': source, 'error': str(error)})
            record['reason'] = 'No substantive identity-verified abstract retrieved; access errors are not absence evidence'
            return record

        print('NETWORK REMAINING', len(pending), flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(retrieve, target): target['key'] for target in pending}
            for count, future in enumerate(as_completed(futures), 1):
                record = future.result()
                outcomes[record['key']] = record
                if count % 10 == 0 or count == len(futures):
                    atomic_json(outcome_path, list(outcomes.values()))
                    print('RECOVERY', count, '/', len(futures), Counter(record['status'] for record in outcomes.values()), flush=True)
    summary = {'created_at': datetime.now(timezone.utc).isoformat(), 'targets': len(targets),
               'statuses': dict(Counter(record['status'] for record in outcomes.values())),
               'selected_recovered': sum(target['selected'] and outcomes.get(target['key'], {}).get('status') == 'recovered' for target in targets),
               'unattempted': len(targets) - len(outcomes), 'local_pubmed_records': len(records)}
    atomic_json(run / 'recovery_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
