"""Stage source-verified historical author metadata and reconcile weekly payloads.

No inference from emails, coauthors or current author profiles. Dates, abstracts,
titles and LLM assessments are preserved. Publication identity is checked before
using PubMed/Europe PMC records. Applying stages creates local source backups.
"""
import argparse
from collections import Counter
import copy
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from affiliation_matcher import AffiliationMatcher,normalize
from enrich_source_metadata import author_name_matches,parse_pubmed_root,normalize_orcid
from ror_refine_batch import ror_refine_paper
from thefuzz import fuzz
from dateutil import parser as date_parser


def canonical_doi(value):
    return re.sub(r'^https?://(?:dx\.)?doi\.org/','',str(value or '').strip(),flags=re.I).lower()


def projection_score(paper,stored):
    old,new=canonical_doi(stored.get('doi')),canonical_doi(paper.get('doi'))
    if old and new and old!=new:return -1
    if stored.get('pmid') and paper.get('pmid') and str(stored['pmid'])!=str(paper['pmid']):return -1
    score=100*bool(old and old==new)+50*bool(stored.get('pmid') and str(stored['pmid'])==str(paper.get('pmid')))
    url=lambda v:re.sub(r'^https?://','',str(v or '')).rstrip('/')
    if stored.get('url') and url(stored['url'])==url(paper.get('url')):score+=25
    day=date_parser.parse(paper['date']).date().isoformat() if paper.get('date') else None
    journal=(paper.get('source') or paper.get('journal') or '').split('+')[0].strip()
    if day==stored.get('pub_date') and journal==str(stored.get('journal') or '').strip():score+=10
    return score


def valid_source(paper,record):
    old,new=canonical_doi(paper.get('doi')),canonical_doi(record.get('doi'))
    if old and new and old!=new:return False
    if old and old==new:return True
    return fuzz.ratio(normalize(paper['title']),normalize(html.unescape(record.get('title',''))))>=95


def epmc_record(record):
    details=[]
    for author in record.get('authorList',{}).get('author',[]):
        name=' '.join(v for v in [author.get('firstName'),author.get('lastName')] if v) or author.get('fullName')
        if not name:continue
        affiliations=[a['affiliation'] for a in author.get('authorAffiliationDetailsList',{}).get('authorAffiliation',[]) if a.get('affiliation')]
        info={'name':name,'affiliation':'; '.join(affiliations),'source':'Europe PMC indexed publication metadata',
              'source_url':f"https://europepmc.org/article/{record['source']}/{record['id']}"}
        orcid=author.get('authorId') or {}
        if orcid.get('type')=='ORCID':
            identifier=normalize_orcid(orcid.get('value'))
            if identifier:info['orcid']=identifier
            elif orcid.get('value'):info['invalid_source_orcid']=orcid['value']
        details.append(info)
    return {'title':record.get('title',''),'doi':record.get('doi'),'pmid':record.get('pmid'),
            'pmcid':record.get('pmcid'),'author_details':details,'record_source':record.get('source')}


def source_affiliations(value):
    values=value if isinstance(value,list) else str(value or '').split(';')
    return [str(v).strip() for v in values if str(v).strip() and str(v).strip().lower() not in {'none','n/a','null','unknown'}]


def publication_source(author):
    source=str(author.get('source','')).lower()
    return any(s in source for s in ['pubmed','europe pmc','europepmc','publisher','citation metadata','biorxiv','arxiv'])


def supplement_paper(paper,pubmed,epmc,preprints,arxiv=None):
    paper=copy.deepcopy(paper)
    old=paper.get('author_details') or paper.get('authors_enriched') or [{'name':n} for n in paper.get('authors',[])]
    audit={'title':paper['title'],'source':paper.get('source'),'before_authors':len(old),
           'before_affiliated_authors':sum(bool(source_affiliations(a.get('affiliation'))) for a in old)}
    record=pubmed.get(str(paper.get('pmid','')))
    if record and not valid_source(paper,record):
        audit['pubmed_identity_rejected']=True;record=None
    options=[epmc_record(r) for r in epmc.get(canonical_doi(paper.get('doi')),[]) if valid_source(paper,r)]
    if not record and len(options)==1:record=options[0]
    verified=bool(record and record.get('author_details'))
    if verified:
        details=copy.deepcopy(record['author_details'])
        if record.get('pmid') and not paper.get('pmid'):paper['pmid']=record['pmid']
        if record.get('pmcid') and not paper.get('pmcid'):paper['pmcid']=record['pmcid']
        for author in details:
            candidates=[a for a in old if author_name_matches(a.get('name',''),author['name'])]
            if len(candidates)==1:
                previous=candidates[0]
                if publication_source(previous):
                    values=source_affiliations(author.get('affiliation'))+source_affiliations(previous.get('affiliation'))
                    author['affiliation']='; '.join(dict.fromkeys(values))
                if any(previous.get(k) for k in ['h_index','citations','orcid']):
                    author['legacy_profile']={k:previous[k] for k in ['name','source','orcid','h_index','citations','affiliation'] if previous.get(k) is not None}
        paper['original_authors']=paper.get('original_authors') or copy.deepcopy(paper.get('authors',[]))
        paper['authors']=[a['name'] for a in details]
        paper['source_author_metadata_status']='verified publication record'
        paper['source_author_list_status']='verified publication record'
    else:
        source_names=[n.get('name') if isinstance(n,dict) else n for n in paper.get('authors',[])]
        source_names=[n for n in source_names if n]
        details=[]
        if source_names:
            for name in source_names:
                candidates=[a for a in old if author_name_matches(a.get('name',''),name)]
                author=copy.deepcopy(candidates[0]) if len(candidates)==1 else {}
                author['name']=name;details.append(author)
            paper['source_author_list_status']='original source author list retained'
        else:
            details=copy.deepcopy(old)
            paper['source_author_list_status']='unresolved'
        for author in details:
            if not publication_source(author):
                if author.get('affiliation'):
                    author['legacy_affiliation']=author.pop('affiliation')
                    author['affiliation_recheck_status']='Current/legacy author profile is not publication affiliation evidence.'
                if author.get('orcid'):
                    author['legacy_profile_orcid']=author.pop('orcid')
                    author['identifier_review_status']='Legacy author-profile ORCID lacks publication-assigned evidence; excluded from identity matching.'
        paper['legacy_author_details']=copy.deepcopy(old)
        paper['source_author_metadata_status']='existing source or unresolved'
    if paper.get('authors_enriched'):
        paper['legacy_authors_enriched']=paper.pop('authors_enriched')
    if paper.get('source')=='arXiv' and arxiv:
        record=arxiv.get(paper.get('url'))
        if record and valid_source(paper,record):
            for author in details:
                candidates=[a for a in record['author_details'] if author_name_matches(author.get('name',''),a['name'])]
                if len(candidates)==1:
                    author.update(candidates[0])
            audit['arxiv_html_matched']=bool(record['author_details'])
    if paper.get('source')=='bioRxiv':
        matches=[epmc_record(r) for r in preprints.get(canonical_doi(paper.get('doi')),[]) if valid_source(paper,r)]
        if len(matches)==1:
            # Keep the stored version's author list; only uniquely matching authors
            # receive explicitly assigned affiliations from the indexed record.
            for author in details:
                candidates=[a for a in matches[0]['author_details'] if author_name_matches(author.get('name',''),a['name'])]
                if len(candidates)==1:
                    matched=candidates[0]
                    if matched.get('affiliation'):
                        author['affiliation']='; '.join(dict.fromkeys(source_affiliations(author.get('affiliation'))+source_affiliations(matched['affiliation'])))
                        author['source']=matched['source'];author['source_url']=matched['source_url']
                        author['affiliation_version_scope']='Indexed preprint metadata; original stored author list retained.'
                    if matched.get('orcid'):
                        author['orcid']=matched['orcid'];author['identifier_source']=matched['source']
                        author['identifier_source_url']=matched['source_url']
            audit['preprint_metadata_matched']=True
        corresponding=paper.get('author_corresponding');unit=paper.get('author_corresponding_institution')
        if corresponding and source_affiliations(unit):
            candidates=[a for a in details if author_name_matches(a.get('name',''),corresponding)]
            if len(candidates)==1:
                author=candidates[0]
                author['affiliation']='; '.join(dict.fromkeys(source_affiliations(author.get('affiliation'))+source_affiliations(unit)))
                author['source_url']=author.get('source_url') or paper.get('url')
                author['source']='bioRxiv corresponding author metadata'
    paper['author_details']=details
    orcid_names={}
    for author in details:
        if author.get('orcid'):orcid_names.setdefault(author['orcid'],set()).add(author['name'])
    conflicts={identifier for identifier,names in orcid_names.items()
               if any(not author_name_matches(a,b) for a in names for b in names)}
    for author in details:
        if author.get('orcid') in conflicts:
            author['conflicting_source_orcid']=author.pop('orcid')
            author['identifier_review_status']='Same publication assigns this ORCID to distinct author names; not used as an identity key.'
    audit['conflicting_source_orcids']=len(conflicts)
    paper['affiliations']=list(dict.fromkeys(v for a in details for v in source_affiliations(a.get('affiliation'))))
    if not any(a.get('h_index') for a in details):
        if paper.get('senior_authors'):paper['legacy_senior_authors']=paper['senior_authors']
        paper['senior_authors']=[]
    paper['author_metrics_status']='Source identity and affiliation backfill; legacy profile metrics not revalidated.'
    paper['author_metadata_verified_on']='2026-10-08'
    audit.update(after_authors=len(details),after_affiliated_authors=sum(bool(source_affiliations(a.get('affiliation'))) for a in details),
                 source_verified=verified,source_orcids=sum(bool(a.get('orcid')) and bool(publication_source(a) or a.get('identifier_source')) for a in details))
    return paper,audit


def identity_titles(path):
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,list):return set()
    return {normalize(r.get('paper',{}).get('title') or r.get('paper',{}).get('raw_data',{}).get('title')) for r in data}


def refine_staged(run):
    """Re-evaluate registry matches without altering source-author audit baselines."""
    manifest=json.loads((run/'author_backfill.json').read_text(encoding='utf-8'))
    matcher=AffiliationMatcher();projection={};scores={};variants=Counter()
    with sqlite3.connect((ROOT/'data/literature.db').as_uri()+'?mode=ro',uri=True) as conn:
        stored={r[0]:dict(zip(['doi','pmid','url','pub_date','journal'],r[1:]))
                for r in conn.execute('SELECT title,doi,pmid,url,pub_date,journal FROM articles')}
    for week in manifest['weeks']:
        refined_path=next(Path(s) for s,t in week['staged_outputs'] if '_enriched_ror_refined.jsonl' in s)
        source_path=next(Path(s) for s,t in week['staged_outputs'] if s.endswith('_enriched.jsonl'))
        papers=[json.loads(l) for l in source_path.read_text(encoding='utf-8').splitlines() if l.strip()]
        for paper in papers:
            ror_refine_paper(paper,matcher)
            score=projection_score(paper,stored[paper['title']])
            if score>0 and score>=scores.get(paper['title'],-1):
                projection[paper['title']]=paper;scores[paper['title']]=score
            else:variants[paper['title']]+=1
        refined_path.write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in papers),encoding='utf-8')
        result_path=next(Path(s) for s,t in week['staged_outputs'] if Path(t).name.startswith('LLM_results_'))
        results=json.loads(result_path.read_text(encoding='utf-8'));by_title={normalize(p['title']):p for p in papers}
        digest=lambda rows:hashlib.sha256(json.dumps([{k:v for k,v in r.items() if k!='paper'} for r in rows],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        before=digest(results)
        for result in results:
            key=normalize(result['paper']['raw_data']['title'])
            result['paper']['raw_data']=by_title[key]
        if before!=digest(results) or before!=week['assessment_digest']:
            raise ValueError('Assessment digest changed during registry refinement')
        result_path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(week['week'],'registry refinement complete',flush=True)
    if set(projection)!=set(stored):raise ValueError('Registry refinement lost stored article identities')
    (run/'all_refined.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in projection.values()),encoding='utf-8')
    manifest['stored_identifier_variant_choices']=dict(variants)
    (run/'author_backfill.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--refine-only',action='store_true',help='Refresh existing stages against the updated registry; preserve source audit baselines')
    parser.add_argument('--from-backups',action='store_true',help='Repeat source staging from this run original backups')
    args=parser.parse_args();run=args.run_dir;run.mkdir(parents=True,exist_ok=True)
    if args.refine_only:
        if args.apply:raise ValueError('Refine and apply are separate steps')
        refine_staged(run);return
    if args.apply:
        manifest=json.loads((run/'author_backfill.json').read_text(encoding='utf-8'))
        for row in manifest['weeks']:
            for source,target in row['staged_outputs']:
                target=Path(target);backup=run/'source_backups'/target.relative_to(ROOT)
                backup.parent.mkdir(parents=True,exist_ok=True)
                if not backup.exists():shutil.copy2(target,backup)
                shutil.copy2(source,target)
        print('Applied staged outputs for',len(manifest['weeks']),'weeks');return
    pubmed={}
    for path in sorted((ROOT/'tmps').glob('**/pubmed_*.xml')):
        try:pubmed.update(parse_pubmed_root(ET.fromstring(path.read_bytes())))
        except ET.ParseError:continue
    epmc=json.loads((run/'doi_records.json').read_text(encoding='utf-8'))
    preprints=json.loads((run/'preprint_records.json').read_text(encoding='utf-8')) if (run/'preprint_records.json').exists() else {}
    arxiv=json.loads((run/'arxiv_records.json').read_text(encoding='utf-8')) if (run/'arxiv_records.json').exists() else {}
    matcher=AffiliationMatcher();manifest={'weeks':[],'pubmed_records':len(pubmed),'paper_audits':[]};all_refined={}
    with sqlite3.connect((ROOT/'data/literature.db').as_uri()+'?mode=ro',uri=True) as conn:
        database_rows={r[0]:dict(zip(['doi','pmid','url','pub_date','journal'],r[1:]))
                       for r in conn.execute('SELECT title,doi,pmid,url,pub_date,journal FROM articles')}
    projection_variants=Counter()
    projection_scores={}
    result_paths=[p for p in (ROOT/'LLM_Results').glob('LLM_results_*.json') if re.match(r'LLM_results_\d{8}',p.name) and not any(w in p.name for w in ['deprecated','.raw','wechat','specialissue'])]
    result_titles={p:identity_titles(p) for p in result_paths}
    for path in sorted((ROOT/'getfiles').glob('all_papers_*_enriched_ror_refined.jsonl')):
        source_path=run/'source_backups'/path.relative_to(ROOT) if args.from_backups else path
        papers=[json.loads(l) for l in source_path.read_text(encoding='utf-8').splitlines() if l.strip()]
        week=re.search(r'\d{4}-\d{2}-\d{2}',path.name)[0];folder=run/'staged'/week;folder.mkdir(parents=True,exist_ok=True)
        titles={normalize(p['title']) for p in papers}
        overlaps=sorted(((len(titles&v)/max(len(titles),len(v)),p) for p,v in result_titles.items()),reverse=True)
        if not overlaps or len(titles&result_titles[overlaps[0][1]])!=len(result_titles[overlaps[0][1]]):
            raise ValueError('No fully aligned weekly result payload: '+path.name)
        result_path=overlaps[0][1]
        result_source=run/'source_backups'/result_path.relative_to(ROOT) if args.from_backups else result_path
        results=json.loads(result_source.read_text(encoding='utf-8'))
        before_hash=hashlib.sha256(json.dumps([{k:v for k,v in r.items() if k!='paper'} for r in results],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        enriched=[];refined=[];audits=[]
        for original in papers:
            paper,audit=supplement_paper(original,pubmed,epmc,preprints,arxiv);enriched.append(copy.deepcopy(paper))
            ror_refine_paper(paper,matcher);refined.append(paper);audits.append(audit)
            # Article primary keys are title-based in this repository. Latest
            # occurrence controls the database projection, while every issue is retained.
            stored=database_rows.get(paper['title'])
            if stored is None:raise ValueError('Historical article missing from database: '+paper['title'])
            score=projection_score(paper,stored)
            if score>0 and score>=projection_scores.get(paper['title'],-1):
                all_refined[paper['title']]=paper;projection_scores[paper['title']]=score
            else:projection_variants[paper['title']]+=1
            for field in ['title','date','doi','abstract']:
                if paper.get(field)!=original.get(field):raise ValueError('Unexpected article change: '+field)
        by_title={normalize(p['title']):p for p in refined}
        adapted=0
        for result in results:
            paper=result.get('paper',{});key=normalize(paper.get('title') or paper.get('raw_data',{}).get('title'))
            if key in by_title:
                paper['raw_data']=by_title[key];paper['authors']=by_title[key]['authors'];adapted+=1
        after_hash=hashlib.sha256(json.dumps([{k:v for k,v in r.items() if k!='paper'} for r in results],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if before_hash!=after_hash or adapted!=len(results):raise ValueError('Result/assessment reconciliation failed for '+week)
        staged=[]
        for filename,data,target in [(path.name,refined,path),(path.name.replace('_enriched_ror_refined','_enriched'),enriched,path.with_name(path.name.replace('_enriched_ror_refined','_enriched')))]:
            output=folder/filename;output.write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in data),encoding='utf-8');staged.append((str(output),str(target)))
        output=folder/result_path.name;output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');staged.append((str(output),str(result_path)))
        profile=Counter()
        for audit in audits:
            for k in ['before_authors','before_affiliated_authors','after_authors','after_affiliated_authors','source_verified','source_orcids']:profile[k]+=audit[k]
        manifest['weeks'].append({'week':week,'papers':len(papers),'result_records':len(results),'profile':dict(profile),
                                  'assessments_preserved':True,'assessment_digest':after_hash,'staged_outputs':staged})
        manifest['paper_audits'].extend(dict(week=week,**a) for a in audits)
        print(week,dict(profile),flush=True)
    (run/'all_refined.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in all_refined.values()),encoding='utf-8')
    manifest['unique_database_titles']=len(all_refined)
    manifest['stored_identifier_variant_choices']=dict(projection_variants)
    if set(all_refined)!=set(database_rows):
        raise ValueError('Some stored article identities have no aligned historical source variant')
    (run/'author_backfill.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
