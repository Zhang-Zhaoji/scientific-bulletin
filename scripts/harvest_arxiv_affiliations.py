"""Harvest only explicitly marked author affiliations from original arXiv HTML.

Unavailable pages and unmapped layouts are recorded. HTML body downloads are
transient; the source author block, title, URL and SHA-256 form the cached evidence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from source_author_parsers import parse_arxiv_authors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args();cache=args.run_dir/'arxiv_cache';cache.mkdir(exist_ok=True)
    papers={p.get('url'):p for p in [json.loads(l) for l in args.input.read_text(encoding='utf-8').splitlines()]
            if p.get('source')=='arXiv' and p.get('url')}
    def retrieve(paper):
        url=re.sub(r'^http:','https:',paper['url']).replace('/abs/','/html/')
        target=cache/(hashlib.sha256(url.encode()).hexdigest()[:20]+'.json')
        if target.exists():data=json.loads(target.read_text(encoding='utf-8'))
        else:
            data={'url':url,'source_url':paper['url']}
            try:
                r=requests.get(url,timeout=25);data['status']=r.status_code
                if r.status_code==200:
                    soup=BeautifulSoup(r.content,'html.parser');block=soup.select_one('.ltx_authors');title=soup.select_one('.ltx_title_document') or soup.find('title')
                    data.update(author_block=str(block) if block else '',title=str(title) if title else '',
                                source_sha256=hashlib.sha256(r.content).hexdigest())
                else:data['availability']='Original HTML endpoint unavailable in this attempt.'
            except requests.RequestException as error:data['error']=str(error)
            target.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            time.sleep(.5)
        parsed=parse_arxiv_authors(data.get('title','')+data.get('author_block',''),paper.get('authors',[]),url)
        return paper['url'],{k:v for k,v in data.items() if k not in {'author_block','title'}},parsed
    records={};audit=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(retrieve,p) for p in papers.values()]
        for future in as_completed(futures):
            url,evidence,parsed=future.result();records[url]=parsed;audit.append(dict(evidence,authors_with_affiliation=len(parsed['author_details'])))
            if len(audit)%25==0:print('arXiv',len(audit),'/',len(papers),'mapped author units',sum(a['authors_with_affiliation'] for a in audit),flush=True)
    (args.run_dir/'arxiv_records.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
    (args.run_dir/'arxiv_fetch_audit.json').write_text(json.dumps({'requested':len(papers),
        'status_counts':dict(Counter(str(a.get('status','error')) for a in audit)),
        'authors_with_affiliation':sum(a['authors_with_affiliation'] for a in audit),'pages':audit},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
