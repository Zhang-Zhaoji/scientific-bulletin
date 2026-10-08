"""Compare city-rule rewrite coverage at publication, address and country-address grains."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from sql_scripts.build_sqlite import normalize_country_name


def load(path):
    return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]


def address_key(value):
    return re.sub(r'\s+',' ',str(value or '')).strip().casefold()


def profile(papers):
    addresses={};countries=Counter();located_papers=0;papers_with_address=0;city_papers=0;authors=0;affiliated_authors=0
    occurrences=0;located_occurrences=0
    for paper in papers:
        pc={normalize_country_name(c) for c in paper.get('countries',[]) if c}
        countries.update(pc);located_papers+=bool(pc);has_address=False;has_city=False
        for author in paper.get('author_details',[]):
            authors+=1;affiliated=False
            for resolution in author.get('affiliation_resolution',[]):
                key=address_key(resolution.get('input'))
                if not key:continue
                has_address=True;affiliated=True;occurrences+=1
                cs={normalize_country_name(c) for c in resolution.get('countries',[]) if c}
                located_occurrences+=bool(cs)
                if key not in addresses:addresses[key]={'address':resolution['input'],'countries':set(),'cities':set(),'statuses':set(),'warnings':[], 'ambiguities':[], 'papers':set(),'examples':[]}
                a=addresses[key];a['countries'].update(cs);a['papers'].add(paper['title']);a['statuses'].add(resolution.get('city_status','not_evaluated'))
                example={'title':paper['title'],'source_url':author.get('source_url') or paper.get('url')}
                if example not in a['examples'] and len(a['examples'])<3:a['examples'].append(example)
                for city in resolution.get('cities',[]):a['cities'].add((city['id'],city['name'],city['country_code']))
                has_city|=bool(resolution.get('cities'))
                for warning in resolution.get('geography_warnings',[]):
                    if warning not in a['warnings']:a['warnings'].append(warning)
                for ambiguity in resolution.get('city_ambiguities',[]):
                    if ambiguity not in a['ambiguities']:a['ambiguities'].append(ambiguity)
            affiliated_authors+=affiliated
        papers_with_address+=has_address;city_papers+=has_city
    located=sum(bool(a['countries']) for a in addresses.values());pairs=sum(len(a['countries']) for a in addresses.values())
    summary={'unique_papers':len(papers),'papers_with_country':located_papers,
             'paper_country_coverage_pct':round(100*located_papers/len(papers),3),
             'papers_with_address_text':papers_with_address,'papers_with_city':city_papers,
             'author_records':authors,'authors_with_address_text':affiliated_authors,
             'address_occurrences':occurrences,'address_occurrences_with_country':located_occurrences,
             'distinct_addresses':len(addresses),'distinct_addresses_with_country':located,
             'address_country_coverage_pct':round(100*located/len(addresses),3),
             'country_address_pairs':pairs,'represented_countries_and_regions':len(countries),
             'distinct_addresses_with_city':sum(bool(a['cities']) for a in addresses.values()),
             'address_city_coverage_pct':round(100*sum(bool(a['cities']) for a in addresses.values())/len(addresses),3),
             'distinct_addresses_with_city_ambiguities':sum(bool(a['ambiguities']) for a in addresses.values()),
             'addresses_with_geography_warnings':sum(bool(a['warnings']) for a in addresses.values())}
    return summary,addresses,countries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--applied',action='store_true')
    args=parser.parse_args();run=args.run_dir
    before_papers=load(run/'before_all_refined.jsonl');after_papers=load(args.after)
    old={p['title']:p for p in before_papers};new={p['title']:p for p in after_papers}
    assert old.keys()==new.keys() and len(new)==len(after_papers)
    for title in old:
        assert all(old[title].get(k)==new[title].get(k) for k in ['title','date','doi','pmid','url','abstract','authors','affiliations']),title
        derived={'ror_normalized_affiliation','ror_match_score','ror_country','ror_subregion','affiliation_resolution'}
        source_authors=lambda p:[{k:v for k,v in a.items() if k not in derived} for a in p.get('author_details',[])]
        assert source_authors(old[title])==source_authors(new[title]),title
    before,ba,bc=profile(before_papers);after,aa,ac=profile(after_papers)
    assert ba.keys()==aa.keys(),'Original source address set changed'
    gains=[{'address':aa[k]['address'],'countries_before':sorted(ba[k]['countries']),'countries_after':sorted(aa[k]['countries']),
            'cities':[{'id':i,'name':n,'country_code':c} for i,n,c in sorted(aa[k]['cities'])],
            'warnings':aa[k]['warnings'],'papers':sorted(aa[k]['papers'])} for k in aa if not ba[k]['countries'] and aa[k]['countries']]
    changes=[{'address':aa[k]['address'],'before':sorted(ba[k]['countries']),'after':sorted(aa[k]['countries']),
              'warnings':aa[k]['warnings'],'papers':sorted(aa[k]['papers'])} for k in aa if ba[k]['countries']!=aa[k]['countries']]
    review=[{'address':a['address'],'countries':sorted(a['countries']),
             'cities':[{'id':i,'name':n,'country_code':c} for i,n,c in sorted(a['cities'])],
             'city_ambiguities':a['ambiguities'],'warnings':a['warnings'],'source_examples':a['examples'],
             'review_status':'pending; no LLM call performed'}
            for a in aa.values() if not a['countries'] or not a['cities'] or a['warnings'] or a['ambiguities']]
    paper_gains=[t for t in new if not old[t].get('countries') and new[t].get('countries')]
    paper_losses=[t for t in new if old[t].get('countries') and not new[t].get('countries')]
    per_country=[]
    for c in sorted(set(bc)|set(ac)):
        per_country.append({'country':c,'papers_before':bc[c],'papers_after':ac[c],
                            'addresses_after':sum(c in a['countries'] for a in aa.values())})
    # Avoid retaining repeated address/country evidence as fake independent events.
    output={'status':'applied' if args.applied else 'staged','verified_on':'2026-10-08','regular_issues':30,
            'definitions':{'paper':'One original database publication identity; repeated weekly appearances are deduplicated.',
                           'address':'Nonempty publication affiliation segment, split at semicolons; whitespace and case are normalized for deduplication.',
                           'country_address_pair':'One distinct normalized country and address pair; multinational addresses may contribute multiple pairs.',
                           'coverage':'Observed fields populated by the rule; this is not measured accuracy. Missing source addresses do not enter the address denominator.'},
            'before':before,'after':after,'net_new_located_addresses':after['distinct_addresses_with_country']-before['distinct_addresses_with_country'],
            'newly_located_addresses':gains,'address_country_changes':changes,
            'newly_located_papers':paper_gains,'lost_country_papers':paper_losses,
            'per_country':per_country,'new_countries_and_regions':sorted(set(ac)-set(bc)),
            'source_metadata_and_author_lists_preserved':True,'source_author_affiliations_and_identifiers_preserved':True,
            'geography_review_queue':{'file':'getfiles/geography_review_queue_2026-10-08.jsonl','distinct_address_items':len(review)},
            'country_logic':'Explicit addresses, independently resolved ROR entities, or unique city constrained by state/country. City/postal conflicts remain recorded.',
            'llm_calls_performed':0,'source_hashes':{'before':hashlib.sha256((run/'before_all_refined.jsonl').read_bytes()).hexdigest(),
                                                   'after':hashlib.sha256(args.after.read_bytes()).hexdigest()}}
    with sqlite3.connect((ROOT/'data/world_cities.db').as_uri()+'?mode=ro',uri=True) as city_conn:
        output['city_index_coverage']={
            'country_codes':city_conn.execute('SELECT COUNT(*) FROM countries').fetchone()[0],
            'countries_and_regions_with_city_records':city_conn.execute('SELECT COUNT(DISTINCT country_code) FROM cities').fetchone()[0],
            'city_records':city_conn.execute('SELECT COUNT(*) FROM cities').fetchone()[0],
            'postal_countries':[r[0] for r in city_conn.execute('SELECT DISTINCT country_code FROM postcodes ORDER BY 1')],
            'coverage_note':'Country code inventory includes territories and historical codes. City coverage excludes settlements below the dataset threshold; postal validation currently covers only US and DE.'}
    if args.applied:
        old_conn=sqlite3.connect((run/'before_literature.db').resolve().as_uri()+'?mode=ro',uri=True)
        conn=sqlite3.connect((ROOT/'data/literature.db').as_uri()+'?mode=ro',uri=True)
        assert list(old_conn.execute('SELECT * FROM articles ORDER BY id'))==list(conn.execute('SELECT * FROM articles ORDER BY id'))
        assert conn.execute('SELECT COUNT(DISTINCT article_id) FROM article_countries').fetchone()[0]==after['papers_with_country']
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not conn.execute('PRAGMA foreign_key_check').fetchall()
        output['database_article_ids_metadata_scores_preserved']=True
    path=ROOT/'getfiles/city_rule_rewrite_audit_2026-10-08.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'getfiles/geography_review_queue_2026-10-08.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in review),encoding='utf-8')
    print(json.dumps({k:output[k] for k in ['status','before','after','net_new_located_addresses','new_countries_and_regions']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
