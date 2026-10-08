"""Refresh derived affiliations for an explicitly selected corpus, preserving articles.

Only selected article-to-country/institution links are replaced. Author affiliation
links shared with unselected historical articles have no per-paper provenance in
the legacy schema, so they are retained and reported rather than silently removed.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from affiliation_matcher import AffiliationMatcher,normalize
from sql_scripts.build_sqlite import normalize_country_name, resolved_author_institutions, ensure_affiliation_schema
from enrich_source_metadata import author_name_matches,normalize_orcid
from dateutil import parser as date_parser
from scripts.update_bulletin_database import (
    Importer, backup_database, fingerprint, readonly, scalar, snapshot, verify_same_article,
)
from sql_scripts.build_slim_db import build_slim_db, verify_slim_db


def article_links(conn, table, right, ids):
    return {row for row in conn.execute(f'SELECT article_id,{right} FROM {table}') if row[0] in ids}


def refresh(conn, papers, matcher):
    if any('affiliation_resolution' not in author for paper in papers
           for author in paper.get('author_details', [])):
        raise ValueError('Input must be reprocessed with the current matcher, including unresolved authors')
    articles_before = list(conn.execute('SELECT * FROM articles ORDER BY id'))
    ensure_affiliation_schema(conn)
    invalid_legacy_orcids=[]
    for ident,orcid in conn.execute('SELECT id,orcid FROM authors WHERE orcid IS NOT NULL').fetchall():
        if not normalize_orcid(orcid):
            invalid_legacy_orcids.append({'author_id':ident,'orcid':orcid,'reason':'Malformed ORCID or invalid check digit.'})
            conn.execute('UPDATE authors SET orcid=NULL WHERE id=?',(ident,))
    # Only names with one independently known ROR identity can seed legacy rows.
    already={r[0] for r in conn.execute('SELECT ror_id FROM institutions WHERE ror_id IS NOT NULL')}
    for ident,name in conn.execute('SELECT id,name FROM institutions WHERE ror_id IS NULL ORDER BY id').fetchall():
        entries=matcher.identities.get(name,[])
        if len(entries)==1 and entries[0]['ror_id'] not in already:
            conn.execute('UPDATE institutions SET ror_id=? WHERE id=?',(entries[0]['ror_id'],ident));already.add(entries[0]['ror_id'])
    lookup = Importer(conn)
    pairs, seen = [], set()
    legacy_title_date_matches=[]
    for paper in papers:
        stored = lookup.resolve_existing_article(paper, recheck=True)
        if stored is None:
            raise ValueError(f'Article missing from database: {paper["title"]}')
        try:
            verify_same_article(stored, paper, allow_url=True)
        except ValueError:
            # Legacy rows may contain no identifiers. A unique unchanged title,
            # publication date and journal tie the original corpus to its stored
            # row; this fallback never permits score/article metadata changes.
            source_date=date_parser.parse(paper['date']).date().isoformat() if paper.get('date') else None
            stored_journal=conn.execute('SELECT journal FROM articles WHERE id=?',(stored['id'],)).fetchone()[0]
            source_journal=(paper.get('source') or paper.get('journal') or '').split('+')[0].strip()
            has_ids=any(stored.get(k) or paper.get(k) for k in ['doi','pmid'])
            if has_ids or stored['title']!=paper['title'] or stored.get('pub_date')!=source_date or str(stored_journal or '').strip()!=source_journal:
                raise
            legacy_title_date_matches.append({'article_id':stored['id'],'title':paper['title'],'pub_date':source_date,
                                              'journal':source_journal,'reason':'Identifiers absent; original unique title/date/journal unchanged.'})
        if stored['id'] in seen:
            raise ValueError('Selected corpus contains duplicated article identity')
        seen.add(stored['id'])
        pairs.append((paper, stored['id']))
    all_author_articles = defaultdict(set)
    for article, author in conn.execute('SELECT article_id,author_id FROM article_authors'):
        all_author_articles[author].add(article)
    exclusive = {a for a, ids in all_author_articles.items() if ids and ids <= seen}
    shared = {a for a, ids in all_author_articles.items() if ids & seen and not ids <= seen}
    before = {t:article_links(conn,t,right,seen) for t,right in (
        ('article_countries','country_id'),('article_institutions','institution_id'))}
    outside = {t:set(conn.execute(f'SELECT article_id,{right} FROM {t}')) - before[t]
               for t,right in (('article_countries','country_id'),('article_institutions','institution_id'))}
    for table in before:
        conn.executemany(f'DELETE FROM {table} WHERE article_id=?',[(i,) for i in seen])
    conn.executemany('DELETE FROM author_institutions WHERE author_id=?',[(a,) for a in exclusive])
    conn.executemany('DELETE FROM article_author_institutions WHERE article_id=?',[(i,) for i in seen])
    # Assess name expansion across the whole selected corpus before reusing IDs.
    old_authors={r[0]:{'name':r[1],'orcid':r[2]} for r in conn.execute('SELECT id,name,orcid FROM authors')}
    previous_by_article=defaultdict(set)
    previous_by_family=defaultdict(lambda:defaultdict(set))
    def family_key(name):
        if ',' in name:return normalize(name.split(',',1)[0]).split()[-1]
        match=re.fullmatch(r'(.+?)\s+[A-Z]{1,6}',name.strip())
        value=match[1] if match else name
        return normalize(value).split()[-1] if normalize(value) else ''
    for article,author in conn.execute('SELECT article_id,author_id FROM article_authors'):
        previous_by_article[article].add(author)
        previous_by_family[article][family_key(old_authors[author]['name'])].add(author)
    suggestions={};bindings=defaultdict(set)
    for paper,article in pairs:
        for index,info in enumerate(paper.get('author_details',[])):
            candidates=[a for a in previous_by_family[article].get(family_key(info.get('name','')),[]) if author_name_matches(old_authors[a]['name'],info.get('name',''))
                        and not (info.get('orcid') and old_authors[a]['orcid'] and info['orcid']!=old_authors[a]['orcid'])]
            if len(candidates)==1:
                suggestions[(article,index)]=candidates[0];bindings[candidates[0]].add(info['name'])
    ambiguous={ident for ident,names in bindings.items()
               if any(not author_name_matches(a,b) for a in names for b in names)}
    name_updates=[]
    for ident,names in bindings.items():
        if ident in ambiguous:continue
        preferred=max(names,key=lambda v:(len(v),v))
        if old_authors[ident]['name']!=preferred and len(preferred)>=len(old_authors[ident]['name']):
            conn.execute('UPDATE authors SET name=? WHERE id=?',(preferred,ident))
            name_updates.append({'author_id':ident,'old_name':old_authors[ident]['name'],'new_name':preferred})
    importer = Importer(conn)
    corrections = []
    stats = Counter()
    for paper_index,(paper, article) in enumerate(pairs,1):
        countries = set(paper.get('countries') or [])
        new_author_ids=set()
        for index,info in enumerate(paper.get('author_details', [])):
            institution_ids = set()
            evidence=defaultdict(list)
            countries.update(info.get('ror_country') or [])
            for row in resolved_author_institutions(info):
                country = importer.country(row['country_name'])
                institution = importer.entity('institutions',{
                    'name':row['name'],'normalized_name':row['normalized_name'],
                    'raw_affiliation':scalar(row['raw_affiliation']),'country_id':country,
                    'ror_id':row.get('ror_id'),
                },preferred_key='ror_id' if row.get('ror_id') else 'normalized_name')
                # Correct a legacy country only when the registry independently
                # gives one country and it agrees with the reviewed resolution.
                registry = {normalize_country_name(matcher.canonical_country(d.get('country_name')))
                            for d in matcher.locations(row['name'])} - {None}
                if country and registry == {normalize_country_name(row['country_name'])}:
                    old = conn.execute('SELECT country_id FROM institutions WHERE id=?',(institution,)).fetchone()[0]
                    if old != country:
                        conn.execute('UPDATE institutions SET country_id=? WHERE id=?',(country,institution))
                        corrections.append({'institution_id':institution,'name':row['name'],
                                            'old_country_id':old,'new_country_id':country,
                                            'evidence':'unique registry country agrees with source resolution'})
                importer.link('article_institutions',article,institution)
                institution_ids.add(institution)
                evidence[institution].append({'affiliation':row['raw_affiliation'],
                                              'source':info.get('source'),'source_url':info.get('source_url') or paper.get('url'),
                                              'ror_id':row.get('ror_id')})
            if info.get('name'):
                preferred=suggestions.get((article,index))
                if preferred in ambiguous:preferred=None
                author=importer.author(article,info,institution_ids,preferred_id=preferred)
                new_author_ids.add(author)
                for institution in institution_ids:
                    conn.execute('''INSERT INTO article_author_institutions(article_id,author_id,institution_id,evidence_json)
                                    VALUES(?,?,?,?) ON CONFLICT(article_id,author_id,institution_id)
                                    DO UPDATE SET evidence_json=excluded.evidence_json''',
                                 (article,author,institution,json.dumps(evidence[institution],ensure_ascii=False,separators=(',',':'))))
                stats['authors_with_institution'] += bool(institution_ids)
        if (paper.get('source_author_metadata_status')=='verified publication record'
                or paper.get('source_author_list_status')=='original source author list retained'):
            for old_author in previous_by_article[article]-new_author_ids:
                conn.execute('DELETE FROM article_authors WHERE article_id=? AND author_id=?',(article,old_author))
                importer.links['article_authors'].discard((article,old_author));importer.article_authors[article].discard(old_author)
                stats['obsolete_author_links_removed']+=1
        for name in countries:
            ident=importer.country(name)
            if ident:
                importer.link('article_countries',article,ident)
        stats['articles_with_country'] += bool(countries)
        if paper_index%500==0:print('Database affiliation refresh',paper_index,'/',len(pairs),flush=True)
    for table,right in (('article_countries','country_id'),('article_institutions','institution_id')):
        after=article_links(conn,table,right,seen)
        current=set(conn.execute(f'SELECT article_id,{right} FROM {table}'))
        if current-after != outside[table]:
            raise RuntimeError('Unselected historical article links changed')
        stats[table+'_removed']=len(before[table]-after)
        stats[table+'_added']=len(after-before[table])
    if list(conn.execute('SELECT * FROM articles ORDER BY id')) != articles_before:
        raise RuntimeError('Article metadata, IDs or scores changed during affiliation refresh')
    return {'selected_articles':len(seen),'statistics':dict(stats),
            'registry_country_corrections':corrections,'exclusive_authors_refreshed':len(exclusive),
            'shared_historical_authors_preserved':len(shared),
            'historical_scope':'Selected publication links and source-verified author lists rebuilt with per-paper affiliation evidence.',
            'author_names_expanded':len(name_updates),'author_name_updates':name_updates,
            'ambiguous_legacy_author_ids_split':len(ambiguous),
            'legacy_title_date_journal_matches':legacy_title_date_matches,
            'invalid_legacy_orcids_quarantined':invalid_legacy_orcids,
            'article_metadata_ids_scores_preserved':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    folder=args.run_dir.resolve()
    if not folder.is_relative_to(ROOT.resolve()):
        raise ValueError('Run directory must be inside the repository')
    folder.mkdir(parents=True,exist_ok=True)
    papers=[json.loads(l) for l in args.input.read_text(encoding='utf-8').splitlines() if l.strip()]
    full=ROOT/'data/literature.db';slim=ROOT/'docs/assets/data/literature_slim.db'
    token=dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    full_backup=folder/f'literature_before_{token}.db';slim_backup=folder/f'literature_slim_before_{token}.db'
    hashes=(fingerprint(full),fingerprint(slim))
    backup_database(full,full_backup);backup_database(slim,slim_backup)
    staged_full=folder/f'literature_staged_{token}.db';staged_slim=folder/f'literature_slim_staged_{token}.db'
    shutil.copy2(full_backup,staged_full)
    with closing(sqlite3.connect(staged_full)) as conn:
        before=snapshot(conn)
        conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN IMMEDIATE')
        audit=refresh(conn,papers,AffiliationMatcher())
        after=snapshot(conn);conn.commit()
        conn.execute('VACUUM')
    build_slim_db(staged_full,staged_slim)
    if not verify_slim_db(staged_full,staged_slim):
        raise RuntimeError('Full/slim reconciliation failed')
    if hashes != (fingerprint(full),fingerprint(slim)):
        raise RuntimeError('Original databases changed concurrently; staged results retained')
    try:
        os.replace(staged_full,full);os.replace(staged_slim,slim)
    except BaseException:
        for backup,target in ((full_backup,full),(slim_backup,slim)):
            restore=folder/('restore_'+backup.name)
            shutil.copy2(backup,restore);os.replace(restore,target)
        raise
    audit.update(status='complete',input=str(args.input),before=before,after=after,
                 backups=[str(full_backup),str(slim_backup)])
    (folder/'database_affiliation_refresh.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k not in {'before','after','registry_country_corrections'}},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
