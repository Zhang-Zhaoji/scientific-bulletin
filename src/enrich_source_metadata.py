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
from affiliation_matcher import normalize
from bs4 import BeautifulSoup
from thefuzz import fuzz

def text(node):
    return ''.join(node.itertext()).strip() if node is not None else ''

def normalized(value):
    return normalize(value).replace(' ', '')


def normalize_orcid(value):
    identifier=re.sub(r'^https?://orcid\.org/','',str(value or '').strip(),flags=re.I).upper()
    if not re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]',identifier):return None
    total=0
    for digit in identifier.replace('-','')[:-1]:total=(total+int(digit))*2
    check=(12-total%11)%11
    if identifier[-1]!=('X' if check==10 else str(check)):return None
    return 'https://orcid.org/'+identifier


def author_name_matches(short, full):
    """Match source names with diacritics and all provided initials, uniquely."""
    if normalized(short) == normalized(full):
        return True
    if ',' in short:
        family, given = short.split(',', 1)
        family = normalize(family).split()
        full_tokens = normalize(full).split()
        if not family or full_tokens[-len(family):] != family:
            return False
        initials = normalize(given).split()
        names = full_tokens[:-len(family)]
        return bool(initials) and len(initials) <= len(names) and all(
            a == b or (len(a)==1 and a==b[0]) or (len(b)==1 and b==a[0])
            for a,b in zip(initials,names))
    if ',' in full:
        return author_name_matches(full, short)
    # PubMed citation strings use family name followed by compact initials.
    for abbreviated,expanded in ((short,full),(full,short)):
        match=re.fullmatch(r'(.+?)\s+([A-Z]{1,6})',abbreviated.strip())
        if match:
            return author_name_matches(match[1]+', '+'. '.join(match[2])+'.',expanded)
    a,b=normalize(short).split(),normalize(full).split()
    if len(a)<2 or len(b)<2 or a[-1]!=b[-1]:
        return False
    given_a,given_b=a[:-1],b[:-1]
    return all(x==y or (len(x)==1 and x==y[0]) or (len(y)==1 and y==x[0])
               for x,y in zip(given_a,given_b))


def merge_author_details(source, indexed):
    merged = copy.deepcopy(indexed)
    for author in merged:
        candidates = [a for a in source if author_name_matches(a['name'], author['name'])]
        if len(candidates) != 1:
            continue
        original = candidates[0]
        affiliations = []
        for record in (author, original):
            values = record.get('affiliation') or []
            if isinstance(values, str):
                values = values.split(';')
            affiliations.extend(str(v).strip() for v in values if str(v).strip())
        if affiliations:
            author['affiliation'] = '; '.join(dict.fromkeys(affiliations))
            author['affiliation_sources'] = list(dict.fromkeys(a.get('source', 'original') for a in (author, original) if a.get('affiliation')))
    return merged

def parse_pubmed_root(root, requested=None):
    records={}
    for article in root.findall('.//PubmedArticle'):
        pmid=text(article.find('MedlineCitation/PMID'))
        if requested is not None and pmid not in requested:
            continue
        details=[]
        for author in article.findall('.//Article/AuthorList/Author'):
            last=text(author.find('LastName'));first=text(author.find('ForeName')) or text(author.find('Initials'))
            name=f'{first} {last}'.strip() if last else text(author.find('CollectiveName'))
            if not name:
                continue
            affiliations=[text(a) for a in author.findall('AffiliationInfo/Affiliation') if text(a)]
            info={'name':name,'affiliation':'; '.join(affiliations),'source':'PubMed XML',
                  'source_url':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'}
            orcids=[text(n).removeprefix('https://orcid.org/').removeprefix('http://orcid.org/')
                    for n in author.findall('Identifier') if n.get('Source','').lower()=='orcid']
            if len(orcids)==1:
                identifier=normalize_orcid(orcids[0])
                if identifier:info['orcid']=identifier
                else:info['invalid_source_orcid']=orcids[0]
            details.append(info)
        doi=next((text(n).lower() for n in article.findall('.//PubmedData/ArticleIdList/ArticleId')
                  if n.get('IdType')=='doi'),'')
        records[pmid]={'title':text(article.find('.//ArticleTitle')),'doi':doi,'author_details':details,
                       'abstract':'\n'.join((a.get('Label','')+': ' if a.get('Label') else '')+text(a)
                                            for a in article.findall('.//Article/Abstract/AbstractText'))}
    return records


def load_pubmed(pmids, cache_dir):
    records = {}
    requested = set(pmids)
    def parse(root):
        records.update(parse_pubmed_root(root,requested))
    # Cache by record identity as well as request batch: removing historical
    # rechecks must not force unchanged source records to be downloaded again.
    for cached in sorted(cache_dir.glob('pubmed_*.xml')):
        parse(ET.fromstring(cached.read_bytes()))
    missing = [p for p in pmids if p not in records]
    for offset in range(0, len(missing), 100):
        batch = missing[offset:offset + 100]
        digest = hashlib.sha256(','.join(batch).encode()).hexdigest()[:12]
        cached = cache_dir / f'pubmed_{digest}.xml'
        response = requests.get('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',
                                params={'db':'pubmed','id':','.join(batch),'retmode':'xml'},timeout=60)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        if root.find('ERROR') is not None:
            raise RuntimeError(text(root.find('ERROR')))
        cached.write_bytes(response.content)
        parse(root)
        time.sleep(0.4)
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
                paper['author_details'] = merge_author_details(paper['author_details'], record['author_details'])
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
                if author_name_matches(short, corresponding):
                    candidates.append(author)
            if len(candidates) == 1:
                candidates[0]['affiliation'] = institution
                candidates[0]['source'] = 'bioRxiv corresponding author metadata'
            elif not candidates:
                # API author lists can be truncated. The explicitly named
                # corresponding author is still direct source metadata.
                detail = {'name':corresponding,'affiliation':institution,
                          'source':'bioRxiv corresponding author metadata',
                          'author_list_status':'supplemented from named corresponding author'}
                paper['author_details'].append(detail)
                if corresponding not in paper['authors']:
                    paper['authors'].append(corresponding)
                paper['source_author_list_warning'] = 'Named corresponding author was absent from API author list.'
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
