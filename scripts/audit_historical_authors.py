"""Validate source backfill, publication identities, editorial preservation and database parity."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from affiliation_matcher import normalize
from refresh_historical_reports import institution_labels
from update_bulletin_database import snapshot


def load_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)


def editorial_blocks(text):
    blocks=re.split(r'(?m)(^### .+$)',text)
    result={}
    for i in range(1,len(blocks),2):
        body=blocks[i+1]
        if '**作者**:' not in body:continue
        body=re.sub(r'(?m)^\*\*(作者|单位|研究地区|资深研究者)\*\*:.*\n?','',body)
        result[normalize(blocks[i].removeprefix('### '))]=re.sub(r'\s+','',body)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args();run=args.run_dir
    manifest=json.loads((run/'author_backfill.json').read_text(encoding='utf-8'))
    reports=json.loads((run/'historical_reports_refresh.json').read_text(encoding='utf-8'))
    report_by_week={r['week']:r for r in reports};weeks=[];totals=Counter();queue={}
    for w in manifest['weeks']:
        refined=next(Path(t) for s,t in w['staged_outputs'] if '_enriched_ror_refined.jsonl' in t)
        old=load_jsonl(run/'source_backups'/refined.relative_to(ROOT));papers=load_jsonl(refined)
        assert len(old)==len(papers)==w['papers'],w['week']
        for before,after in zip(old,papers):
            assert all(before.get(k)==after.get(k) for k in ['title','date','doi','abstract']),after['title']
        result_path=next(Path(t) for s,t in w['staged_outputs'] if Path(t).name.startswith('LLM_results_'))
        results=json.loads(result_path.read_text(encoding='utf-8'))
        digest=hashlib.sha256(json.dumps([{k:v for k,v in r.items() if k!='paper'} for r in results],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        assert digest==w['assessment_digest'] and len(results)==w['result_records'],w['week']
        report=Path(report_by_week[w['week']]['report']);before=(run/'source_backups'/report.relative_to(ROOT)).read_text(encoding='utf-8');after=report.read_text(encoding='utf-8')
        assert before.splitlines()[0]==after.splitlines()[0],report.name
        assert editorial_blocks(before)==editorial_blocks(after),report.name
        assert after.count('> 作者信息回填：')==1 and after.count('### 🌍 国家/地区分布')==1,report.name
        profile=dict(w['profile']);totals.update(profile)
        row={'week':w['week'],'paper_occurrences':len(papers),'author_records':profile,
             'papers_with_source_affiliation_before':sum(bool(p.get('affiliations')) for p in old),
             'papers_with_source_affiliation_after':sum(bool(p.get('affiliations')) for p in papers),
             'papers_with_country_before':sum(bool(p.get('countries')) for p in old),
             'papers_with_country_after':sum(bool(p.get('countries')) for p in papers),
             'papers_with_resolved_institution_after':sum(bool(institution_labels(p,raw_fallback=False)) for p in papers),
             'report':str(report.relative_to(ROOT)),'editorial_blocks_preserved':len(editorial_blocks(before)),
             'assessment_digest_preserved':True,'original_article_fields_preserved':True}
        weeks.append(row)
        for p in papers:
            for a in p.get('author_details',[]):
                for resolution in a.get('affiliation_resolution',[]):
                    if resolution.get('status') not in {'unresolved','ambiguous'}:continue
                    key=(resolution.get('status'),resolution.get('input'))
                    if key not in queue:queue[key]={'status':key[0],'affiliation':key[1],'author_record_occurrences':0,'examples':[],
                                                  'countries':resolution.get('countries',[]),'ambiguities':resolution.get('ambiguous',[]),
                                                  'cities':resolution.get('cities',[]),'city_status':resolution.get('city_status'),
                                                  'city_ambiguities':resolution.get('city_ambiguities',[]),
                                                  'geography_warnings':resolution.get('geography_warnings',[])}
                    entry=queue[key];entry['author_record_occurrences']+=1
                    example={'title':p['title'],'doi':p.get('doi'),'author':a['name'],
                             'source_url':a.get('source_url') or p.get('url')}
                    if example not in entry['examples'] and len(entry['examples'])<3:entry['examples'].append(example)
    baseline=next((run/'database_model_checked').glob('literature_before_*.db'))
    with readonly(baseline) as old_conn,readonly(ROOT/'data/literature.db') as conn,readonly(ROOT/'docs/assets/data/literature_slim.db') as slim:
        assert list(old_conn.execute('SELECT * FROM articles ORDER BY id'))==list(conn.execute('SELECT * FROM articles ORDER BY id'))
        before,after,slim_after=snapshot(old_conn),snapshot(conn),snapshot(slim)
        assert after['counts']==slim_after['counts']
        for check in [after,slim_after]:assert check['integrity_check']=='ok' and check['foreign_key_errors']==0
        assert list(conn.execute('SELECT article_id,author_id,institution_id FROM article_author_institutions ORDER BY 1,2,3'))==list(slim.execute('SELECT article_id,author_id,institution_id FROM article_author_institutions ORDER BY 1,2,3'))
        country_before=old_conn.execute('SELECT COUNT(DISTINCT article_id) FROM article_countries').fetchone()[0]
        country_after=conn.execute('SELECT COUNT(DISTINCT article_id) FROM article_countries').fetchone()[0]
        institution_before=old_conn.execute('SELECT COUNT(DISTINCT article_id) FROM article_institutions').fetchone()[0]
        institution_after=conn.execute('SELECT COUNT(DISTINCT article_id) FROM article_institutions').fetchone()[0]
        evidence_missing=conn.execute('SELECT COUNT(*) FROM article_author_institutions WHERE evidence_json IS NULL OR evidence_json=""').fetchone()[0]
        assert evidence_missing==0
    fetch={}
    for name,excludes in [('pubmed_fetch_audit.json',{'batches','records'}),('arxiv_fetch_audit.json',{'pages'}),('doi_fetch_audit.json',{'records','batches'})]:
        path=run/name
        if path.exists():fetch[name]={k:v for k,v in json.loads(path.read_text(encoding='utf-8')).items() if k not in excludes}
    registry=json.loads((ROOT/'data/RORIndexManifest.json').read_text(encoding='utf-8'))
    result={'status':'verified','verified_on':'2026-10-08','regular_issues':len(weeks),
            'weekly_paper_occurrences':sum(w['paper_occurrences'] for w in weeks),'unique_database_articles':after['counts']['articles'],
            'counting_unit':'Author records count each paper-author occurrence, including repeated papers in weekly archives; they are not unique people.',
            'author_record_totals':dict(totals),'source_orcid_unique':len({a['orcid'] for p in load_jsonl(run/'all_refined.jsonl') for a in p.get('author_details',[]) if a.get('orcid')}),
            'database_country_coverage':{'before':country_before,'after':country_after,'total':after['counts']['articles']},
            'database_institution_coverage':{'before':institution_before,'after':institution_after,'total':after['counts']['articles']},
            'database_before':before,'database_after':after,'full_slim_counts_and_publication_affiliation_links_match':True,
            'article_ids_dates_metadata_scores_preserved':True,'all_editorial_blocks_and_assessments_preserved':True,
            'source_affiliation_evidence_missing':evidence_missing,'ror_index':registry,
            'reviewed_override_organizations':len(json.loads((ROOT/'data/affiliation_overrides.json').read_text(encoding='utf-8'))['institutions']),
            'source_fetch':fetch,'unresolved_affiliation_texts':len(queue),
            'same_title_variant_policy':'Database projection chooses the original stored DOI/PMID/URL identity; each weekly version stays in its archive.',
            'legacy_orcid_policy':'Unverified author-profile identifiers are archived, excluded from publication identity matching; source check digits and within-paper collisions checked.',
            'limitations':['Coverage is not measured accuracy. Missing source affiliations, ambiguous names and absent registry units remain unresolved.',
                           'Preprint index metadata can describe a later version; only uniquely matched authors receive its explicit units or identifiers.',
                           'Legacy h-index/citation metrics were not revalidated.'],
            'baseline_database_backup':str(baseline),'weeks':weeks}
    render=run/'render_qa.json'
    if render.exists():
        result['website_render_validation']=json.loads(render.read_text(encoding='utf-8'))
        assert result['website_render_validation'].get('status')=='passed'
    test_log=run/'all_tests_final.log'
    if test_log.exists():
        log=test_log.read_text(encoding='utf-8');match=re.search(r'Ran (\d+) tests',log)
        assert match and re.search(r'(?m)^OK\s*$',log)
        result['regression_tests']={'passed':int(match[1]),'log':str(test_log)}
    output=ROOT/'getfiles/historical_author_audit_2026-10-08.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    review=ROOT/'getfiles/affiliation_review_queue_2026-10-08.jsonl'
    review.write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in sorted(queue.values(),key=lambda v:-v['author_record_occurrences'])),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k in {'status','regular_issues','weekly_paper_occurrences','unique_database_articles','author_record_totals','database_country_coverage','database_institution_coverage','unresolved_affiliation_texts'}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
