"""Enrich author names, affiliations and abstracts from source metadata, without OpenAlex."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz

def text(node):
    return ''.join(node.itertext()).strip() if node is not None else ''

def normalized(value):
    return re.sub(r'[^\w]', '', value).lower()

def load_pubmed(pmids, cache_dir):
    records = {}
    for offset in range(0, len(pmids), 100):
        batch = pmids[offset:offset + 100]
        digest = hashlib.sha256(','.join(batch).encode()).hexdigest()[:12]
        cached = cache_dir / f'pubmed_{digest}.xml'
        if not cached.exists():
            response = requests.get('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',
                                    params={'db': 'pubmed', 'id': ','.join(batch), 'retmode': 'xml'}, timeout=60)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            if root.find('ERROR') is not None:
                raise RuntimeError(text(root.find('ERROR')))
            cached.write_bytes(response.content)
            time.sleep(0.4)
        root = ET.fromstring(cached.read_bytes())
        for article in root.findall('.//PubmedArticle'):
            pmid = text(article.find('MedlineCitation/PMID'))
            title = text(article.find('.//ArticleTitle'))
            details = []
            for author in article.findall('.//Article/AuthorList/Author'):
                last = text(author.find('LastName'))
                first = text(author.find('ForeName')) or text(author.find('Initials'))
                name = f'{first} {last}'.strip() if last else text(author.find('CollectiveName'))
                if name:
                    affiliations = [text(a) for a in author.findall('AffiliationInfo/Affiliation') if text(a)]
                    details.append({'name': name, 'affiliation': '; '.join(affiliations), 'source': 'PubMed XML'})
            abstract = '\n'.join((a.get('Label', '') + ': ' if a.get('Label') else '') + text(a)
                                 for a in article.findall('.//Article/Abstract/AbstractText'))
            records[pmid] = {'title': title, 'author_details': details, 'abstract': abstract}
        print(f'PubMed source records: {len(records)}', flush=True)
    return records

def enrich(input_path, output_path, cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    papers = [json.loads(line) for line in input_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    pmids = sorted({str(p['pmid']) for p in papers if p.get('pmid')})
    records = load_pubmed(pmids, cache_dir)
    recovered = 0
    for index, paper in enumerate(papers):
        source_details = paper.get('author_details') or []
        paper['author_details'] = copy.deepcopy(source_details) if source_details else [
            {'name': name, 'source': paper.get('source', 'original')}
            for name in paper.get('authors', [])
        ]
        record = records.get(str(paper.get('pmid', '')))
        if record and fuzz.ratio(normalized(record['title']), normalized(paper['title'])) >= 90:
            if record['author_details']:
                paper['original_authors'] = copy.deepcopy(paper['authors'])
                paper['author_details'] = record['author_details']
                paper['authors'] = [a['name'] for a in record['author_details']]
            if len(paper.get('abstract') or '') < 50 and record['abstract']:
                paper['abstract'] = record['abstract']
                paper['abstract_source'] = 'PubMed XML'
                recovered += 1
        corresponding = paper.get('author_corresponding', '')
        institution = paper.get('author_corresponding_institution', '')
        if corresponding and institution:
            candidates = []
            for author in paper['author_details']:
                short = author['name']
                exact = normalized(short) == normalized(corresponding)
                family, separator, initials = short.partition(',')
                initials = normalized(initials)
                abbreviated = (separator and initials and normalized(corresponding).endswith(normalized(family))
                               and normalized(corresponding).startswith(initials[0]))
                if exact or abbreviated:
                    candidates.append(author)
            if len(candidates) == 1:
                candidates[0]['affiliation'] = institution
                candidates[0]['source'] = 'bioRxiv corresponding author metadata'
        if len(paper.get('abstract') or '') < 50 and 'nature' in paper.get('source', '').lower():
            cached = cache_dir / f'publisher_{index:04d}.html'
            try:
                if not cached.exists():
                    url = paper['url']
                    if url.startswith('/'):
                        url = 'https://www.nature.com' + url
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    cached.write_text(response.text, encoding='utf-8')
                    time.sleep(0.4)
                soup = BeautifulSoup(cached.read_text(encoding='utf-8'), 'html.parser')
                paragraphs = soup.select('#Abs1-content p, #Abs1 p, #abstract p')
                abstract = ' '.join(p.get_text(' ', strip=True) for p in paragraphs)
                if len(abstract) > 50:
                    paper['abstract'] = abstract
                    paper['abstract_source'] = 'Original publisher abstract section'
                    recovered += 1
            except requests.RequestException as error:
                print(f'Publisher abstract unavailable: {paper["title"][:60]}: {error}', flush=True)
        paper['affiliations'] = list(dict.fromkeys(a['affiliation'] for a in paper['author_details'] if a.get('affiliation')))
        paper['author_enrichment_status'] = 'enriched'
        paper['author_metrics_status'] = 'not requested; source metadata only'
        paper['senior_authors'] = []
    with output_path.open('w', encoding='utf-8') as stream:
        for paper in papers:
            stream.write(json.dumps(paper, ensure_ascii=False) + '\n')
    audit = {'papers': len(papers), 'authors_present': sum(bool(p.get('authors')) for p in papers),
             'papers_with_affiliation': sum(bool(p['affiliations']) for p in papers),
             'authors_with_affiliation': sum(bool(a.get('affiliation')) for p in papers for a in p['author_details']),
             'abstracts_recovered': recovered, 'missing_abstracts': sum(len(p.get('abstract') or '') < 50 for p in papers),
             'authors_with_metrics': 0, 'author_metrics_status': 'not requested; source metadata only'}
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)
    output_path.with_suffix('.audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('-o', '--output', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, default=Path('tmps/source_metadata'))
    args = parser.parse_args()
    enrich(args.input, args.output, args.cache_dir)
