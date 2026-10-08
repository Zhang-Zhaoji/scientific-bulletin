"""Date-bounded publisher and Europe PMC supplements, with cached source evidence.

This writes a separate temporary JSONL; it never modifies the main crawl output.
Nature uses the publisher's ISO datetime attributes. Other journals use Europe
PMC's firstPublicationDate, never index date or imputed month/issue dates.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from utils import ymd

NATURE_JOURNALS = {
    'nature': 'Nature', 'natbiomedeng': 'Nature BME',
    'nmeth': 'Nature Method', 'neuro': 'Nature Neuroscience',
    'nathumbehav': 'Nature Human Behavior',
}
INDEX_JOURNALS = {
    'Science': 'Science', 'Cell': 'Cell', 'Neuron': 'Neuron',
    'Current Biology': 'Current Biology',
    'Trends in Neurosciences': 'Trends in Neurosciences',
    'Cell Reports': 'Cell Reports', 'iScience': 'iScience',
    'Cell Systems': 'Cell Systems',
}
OTHER_INDEX_JOURNALS = {
    'J Neurophysiol': 'Journal of Neurophysiology',
    'J Neurosci': 'Journal of Neuroscience',
    'J Cogn Neurosci': 'Journal of Cognitive Neuroscience',
    'J Vis': 'Journal of Vision', 'Proc Natl Acad Sci U S A': 'PNAS',
    'Brain': 'Brain', 'Science Advances': 'Science Advances', 'Elife': 'eLife',
    'PLoS Biol': 'PLOS', 'PLoS Comput Biol': 'PLOS', 'PLoS One': 'PLOS',
}
ALLOWED_TYPES = {'Article', 'Review Article', 'Research Article', 'Brief Communication',
                 'Technical Report', 'Resource', 'Analysis'}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) BulletinSourceAudit/1.0'}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def cached_get(url, cache, params=None):
    query = requests.Request('GET', url, params=params).prepare().url
    digest = hashlib.sha256(query.encode()).hexdigest()[:20]
    target = cache / digest
    metadata = cache / f'{digest}.request.json'
    if target.exists():
        return target.read_text(encoding='utf-8'), query
    response = requests.get(url, params=params, headers=HEADERS, timeout=45)
    response.raise_for_status()
    response.encoding = 'utf-8'
    target.write_text(response.text, encoding='utf-8')
    write_json(metadata, {'url': response.url, 'status': response.status_code,
                          'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat()})
    return response.text, response.url


def full_publisher_metadata(paper, cache):
    """Retain listing date and fetch abstract and all citation authors."""
    text, evidence_url = cached_get(paper['url'], cache)
    soup = BeautifulSoup(text, 'html.parser')
    details = []
    for meta in soup.find_all('meta'):
        name, value = meta.get('name', ''), meta.get('content', '').strip()
        if name == 'citation_author' and value:
            details.append({'name': value, 'affiliations': [], 'source': 'publisher citation metadata'})
        elif name == 'citation_author_institution' and details and value:
            details[-1]['affiliations'].append(value)
    if details:
        for author in details:
            author['affiliation'] = '; '.join(author.pop('affiliations'))
        paper['authors'] = [a['name'] for a in details]
        paper['author_details'] = details
    section = soup.find('section', attrs={'data-title': 'Abstract'})
    if section:
        content = section.find('div', class_='c-article-section__content') or section
        for superscript in content.find_all('sup'):
            if superscript.find('a', attrs={'data-test': 'citation-ref'}):
                superscript.decompose()
        paper['abstract'] = ' '.join(p.get_text(' ', strip=True) for p in content.find_all('p'))
    if not paper.get('abstract'):
        meta = soup.find('meta', attrs={'name': 'citation_abstract'})
        paper['abstract'] = meta.get('content', '').strip() if meta else ''
    dates = {}
    for name in ('citation_publication_date', 'citation_online_date', 'dc.date'):
        tag = soup.find('meta', attrs={'name': name})
        if tag:
            dates[name] = tag.get('content', '')
    paper['date_evidence']['article_meta'] = dates
    paper['date_evidence']['article_url'] = evidence_url
    paper['abstract_source'] = 'publisher Abstract section'
    return paper


def publisher_listing(url, source, start, end, cache, max_pages):
    papers, pages, rejected, seen = [], [], Counter(), set()
    for page in range(1, max_pages + 1):
        text, evidence_url = cached_get(url, cache, {'searchType': 'journalSearch', 'sort': 'PubDate', 'page': page})
        soup = BeautifulSoup(text, 'html.parser')
        page_dates, count = [], 0
        for card in soup.find_all('article'):
            heading = card.find('h3')
            link = heading.find('a', href=True) if heading else None
            date_tag = card.find('time', datetime=True)
            if not link or not date_tag:
                continue
            date_raw = date_tag.get('datetime', '')
            try:
                date = dt.date.fromisoformat(ymd(date_raw))
            except ValueError:
                rejected['unknown_date'] += 1
                continue
            page_dates.append(date.isoformat())
            count += 1
            type_tag = card.find('span', class_='c-meta__type') or card.find('span', attrs={'data-test': 'article.type'})
            article_type = type_tag.get_text(' ', strip=True) if type_tag else 'Article'
            if article_type not in ALLOWED_TYPES:
                rejected[f'type:{article_type}'] += 1
                continue
            if not start <= date <= end:
                rejected['outside_window'] += 1
                continue
            article_url = urljoin(url, link['href'])
            if article_url in seen:
                continue
            seen.add(article_url)
            papers.append({'type': article_type, 'title': link.get_text(' ', strip=True),
                           'authors': [a.get_text(' ', strip=True) for a in card.find_all('li', itemprop='creator')],
                           'date': date.isoformat(), 'url': article_url, 'source': source,
                           'doi': '10.1038/' + article_url.rsplit('/', 1)[-1],
                           'date_evidence': {'field': 'publisher time[datetime]', 'value': date_raw,
                                             'listing_url': evidence_url},
                           'retrieval_source': 'publisher listing + article page'})
        pages.append({'page': page, 'article_cards': count, 'min_date': min(page_dates, default=None),
                      'max_date': max(page_dates, default=None), 'url': evidence_url})
        # Inspect a complete page before stopping: cards may not be strictly ordered.
        if not page_dates or max(page_dates) < start.isoformat() or min(page_dates) < start.isoformat():
            break
    return papers, {'source': source, 'url': url, 'pages': pages,
                    'accepted': len(papers), 'rejected': dict(rejected),
                    'status': 'ok', 'page_limit_reached': len(pages) == max_pages}


def index_journal(journal, source, start, end, cache):
    query = f'JOURNAL:"{journal}" AND FIRST_PDATE:[{start} TO {end}] AND SRC:MED'
    papers, raw_results, cursor, pages, hit_count = [], [], '*', 0, None
    while True:
        text, evidence_url = cached_get('https://www.ebi.ac.uk/europepmc/webservices/rest/search', cache,
                                       {'query': query, 'format': 'json', 'resultType': 'core',
                                        'pageSize': 1000, 'cursorMark': cursor})
        data = json.loads(text)
        hit_count = data.get('hitCount', 0)
        results = data.get('resultList', {}).get('result', [])
        raw_results.extend(results)
        pages += 1
        next_cursor = data.get('nextCursorMark')
        if not results or not next_cursor or next_cursor == cursor or len(raw_results) >= hit_count:
            break
        cursor = next_cursor
    rejected = Counter()
    for result in raw_results:
        title = BeautifulSoup(result.get('title', ''), 'html.parser').get_text(' ', strip=True)
        if re.match(r'^(retraction|correction|erratum|expression of concern|in this issue|reply to)\b', title, re.IGNORECASE):
            rejected['non_research_title'] += 1
            continue
        date_raw = result.get('firstPublicationDate', '')
        try:
            date = dt.date.fromisoformat(date_raw)
        except ValueError:
            rejected['unknown_date'] += 1
            continue
        if not start <= date <= end:
            rejected['outside_window'] += 1
            continue
        info = result.get('journalInfo', {})
        journal_record = info.get('journal', {})
        actual_journal = journal_record.get('title', '')
        # JOURNAL searches may tokenize names; reject unrelated matches.
        normalize = lambda value: re.sub(r'[^a-z0-9]', '', value.lower())
        names = {normalize(actual_journal), normalize(re.split(r'[:(]', actual_journal)[0]),
                 normalize(journal_record.get('medlineAbbreviation', ''))}
        if normalize(journal) not in names:
            rejected[f'other_journal:{actual_journal}'] += 1
            continue
        types = result.get('pubTypeList', {}).get('pubType', [])
        if any(value in types for value in ('Published Erratum', 'Retracted Publication', 'Retraction of Publication', 'Editorial', 'Comment')):
            rejected['non_research_type'] += 1
            continue
        authors, details = [], []
        for author in result.get('authorList', {}).get('author', []):
            name = author.get('fullName') or ' '.join(filter(None, (author.get('firstName'), author.get('lastName'))))
            if not name:
                continue
            affiliations = [a.get('affiliation', '') for a in author.get('authorAffiliationDetailsList', {}).get('authorAffiliation', [])]
            authors.append(name)
            details.append({'name': name, 'affiliation': '; '.join(filter(None, affiliations)), 'source': 'Europe PMC core'})
        doi, pmid = result.get('doi', ''), str(result.get('pmid', result.get('id', '')))
        abstract = BeautifulSoup(result.get('abstractText', '') or '', 'html.parser').get_text(' ', strip=True)
        papers.append({'type': 'Review Article' if 'Review' in types else 'Article',
                       'title': title,
                       'date': date.isoformat(), 'authors': authors, 'author_details': details,
                       'abstract': abstract, 'abstract_source': 'Europe PMC indexed journal abstract',
                       'url': 'https://doi.org/' + doi if doi else f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
                       'doi': doi, 'pmid': pmid, 'pmcid': result.get('pmcid', ''), 'journal': actual_journal,
                       'source': source, 'pub_types': types, 'retrieval_source': 'Europe PMC MED core',
                       'date_evidence': {'field': 'firstPublicationDate', 'value': date_raw,
                                         'pubmed_id': pmid, 'query_url': evidence_url,
                                         'electronicPublicationDate': result.get('electronicPublicationDate'),
                                         'printPublicationDate': info.get('printPublicationDate')}})
    return papers, {'source': source, 'query': query, 'hit_count': hit_count, 'pages': pages,
                    'retrieved_records': len(raw_results), 'complete_pagination': len(raw_results) == hit_count,
                    'accepted': len(papers), 'rejected': dict(rejected), 'status': 'ok',
                    'limitation': 'Index coverage only; recent publisher records may not yet be indexed.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--end-date', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--sources', default='nature,science,cell,natcomm,index')
    parser.add_argument('--max-pages', type=int, default=10)
    args = parser.parse_args()
    if args.end_date < args.start_date:
        parser.error('end-date precedes start-date')
    output = args.output_dir or ROOT / f'tmps/pipeline_{args.end_date:%Y%m%d}'
    output.mkdir(parents=True, exist_ok=True)
    cache = output / 'supplement_source_cache'
    cache.mkdir(exist_ok=True)
    selected = set(args.sources.split(','))
    tasks = []
    if 'nature' in selected:
        for slug, name in NATURE_JOURNALS.items():
            for section in ('research-articles', 'reviews-and-analysis'):
                tasks.append(('publisher', f'https://www.nature.com/{slug}/{section}', name))
    if 'natcomm' in selected:
        for section in ('biological-sciences', 'health-sciences'):
            tasks.append(('publisher', f'https://www.nature.com/subjects/{section}/ncomms', 'Nature Communications'))
    for name, source in INDEX_JOURNALS.items():
        if ('science' if name == 'Science' else 'cell') in selected:
            tasks.append(('index', name, source))
    if 'index' in selected:
        for name, source in OTHER_INDEX_JOURNALS.items():
            tasks.append(('index', name, source))
    papers, audits = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for kind, url, source in tasks:
            function = publisher_listing if kind == 'publisher' else index_journal
            params = (url, source, args.start_date, args.end_date, cache)
            if kind == 'publisher':
                params += (args.max_pages,)
            futures[pool.submit(function, *params)] = (url, source)
        for future in as_completed(futures):
            url, source = futures[future]
            try:
                found, audit = future.result()
                papers.extend(found)
                audits.append(audit)
                print(f'{source}: {len(found)} records from {url}', flush=True)
            except Exception as exc:
                audits.append({'source': source, 'url': url, 'status': 'failed', 'error': str(exc)})
                print(f'{source}: failed ({type(exc).__name__})', flush=True)
    unique = {}
    for paper in papers:
        key = paper.get('doi') or paper['url']
        unique.setdefault(key.lower(), paper)
    papers = list(unique.values())
    publisher_papers = [p for p in papers if p['retrieval_source'].startswith('publisher')]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(full_publisher_metadata, paper, cache): paper for paper in publisher_papers}
        for index, future in enumerate(as_completed(futures), 1):
            paper = futures[future]
            try:
                future.result()
            except Exception as exc:
                paper['abstract'] = ''
                paper['metadata_fetch_error'] = str(exc)
            if index % 20 == 0 or index == len(futures):
                print(f'Publisher metadata: {index}/{len(futures)}', flush=True)
    papers.sort(key=lambda p: (p['date'], p['source'], p['title']))
    with (output / 'supplement.jsonl').open('w', encoding='utf-8') as stream:
        for paper in papers:
            stream.write(json.dumps(paper, ensure_ascii=False) + '\n')
    publisher_date_mismatches = []
    index_print_date_differences = []
    for paper in papers:
        evidence = paper['date_evidence']
        online = evidence.get('article_meta', {}).get('citation_online_date')
        if online:
            # Nature citation meta uses YYYY/MM/DD; listing datetime uses ISO.
            online_date = dt.datetime.strptime(online, '%Y/%m/%d').date().isoformat() if '/' in online else dt.date.fromisoformat(online[:10]).isoformat()
            if online_date != paper['date']:
                publisher_date_mismatches.append({'doi': paper.get('doi'), 'listing_date': paper['date'], 'online_date': online_date})
        print_date = evidence.get('printPublicationDate')
        if print_date and print_date != paper['date']:
            index_print_date_differences.append({'doi': paper.get('doi'), 'first_publication_date': paper['date'], 'print_date': print_date})
    audit = {'date_range': [str(args.start_date), str(args.end_date)], 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
             'count': len(papers), 'counts': dict(Counter(p['source'] for p in papers)),
             'missing_abstract_count': sum(not p.get('abstract') for p in papers),
             'publisher_date_mismatches': publisher_date_mismatches,
             'index_print_date_differences': index_print_date_differences,
             'author_affiliation_record_count': sum(bool(a.get('affiliation')) for p in papers for a in p.get('author_details', [])),
             'requests': audits, 'date_parser_diagnosis': 'ISO YYYY-MM-DD must bypass dateutil dayfirst=True.',
             'limitations': ['Nature Communications limited to original biological/health subject pages.',
                             'Europe PMC firstPublicationDate is an indexed first publication date; index completeness is not guaranteed.']}
    write_json(output / 'supplement_audit.json', audit)
    print(json.dumps({k: audit[k] for k in ('count', 'counts', 'missing_abstract_count')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
