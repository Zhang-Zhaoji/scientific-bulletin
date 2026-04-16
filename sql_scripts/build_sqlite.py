import json
import sqlite3
from datetime import datetime
import argparse
import os
import hashlib
import jsonlines
from dateutil import parser

def init_db(db_path="data/literature.db"):
    conn = sqlite3.connect(db_path)
    conn.executescript(open('sql_scripts/schema.sql', 'r', encoding='utf-8').read())
    return conn

'''
One example of an article in the jsonL file:
{"type": "Article", 
"title": "Atomic unification in molecular AI", 
"authors": ["Xiaozhi Fu"], 
"date": "import time", 
"url": "https://www.cell.com/cell/fulltext/S0092-8674(26)00277-1", 
"doi": "10.1016/j.cell.2026.03.010", 
"abstract": "Artificial intelligence has rapidly advanced molecular science, yet progress has largely unfolded through specialized models tailored to specific tasks. In this issue of Cell, Peng et al. introduce PocketXMol, a unified 3D generative framework that reframes molecular design problems as conditional reconstruction of atomic interactions. Demonstrations across design scenarios highlight its potential in molecular engineering.", 
"source": "Cell + Europe PMC", 
"enrichment_status": "europepmc_title", 
"pmid": "41932325", 
"pmcid": "", 
"journal": "", 
"is_open_access": false, 
"affiliations": ["Department Of Life Sciences, Chalmers University Of Technology, Kemivägen 10, Se-412 96 Gothenburg, Sweden", "Electronic Address: Xiaozhi", "Fu@Chalmers"], 
"author_details": [
    {"name": "Xiaozhi Fu", 
    "affiliation": "Department of Life Sciences, Chalmers University of Technology, Kemivägen 10, SE-412 96 Gothenburg, Sweden. Electronic address: xiaozhi.fu@chalmers.se.", 
    "normalized_affiliation": "Department Of Life Sciences, Chalmers University Of Technology, Kemivägen 10, Se-412 96 Gothenburg, Sweden. Electronic Address: Xiaozhi.Fu@Chalmers.Se.", 
    "country": "Sweden", 
    "orcid": null, 
    "h_index": null, 
    "citations": null, 
    "works_count": null, 
    "i10_index": null, 
    "is_senior_researcher": false, 
    "source": "Not found", 
    "last_updated": "2026-04-11T02:34:24.989435", 
    "first_seen": "2026-04-11", 
    "last_seen": "2026-04-11"}
    ], 
"senior_authors": [], 
"senior_author_names": [], 
"senior_author_count": 0, 
"has_senior_researcher": false, 
"countries": ["Sweden"], 
"author_enrichment_status": "enriched"}
'''

def parse_work_details(work_json:dict):
    """
    Parse the work details from the JSON object.
    """
    # first extract article infos:
    ''' 
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    doi TEXT UNIQUE,
    pmid TEXT,
    pmcid TEXT,
    abstract TEXT,
    journal TEXT,
    pub_date TEXT,
    pub_year INTEGER,
    is_open_access BOOLEAN,
    url TEXT,
    '''
    title = work_json.get('title', None)
    doi = work_json.get('doi', None)
    pmid = work_json.get('pmid', None)
    pmcid = work_json.get('pmcid', None)
    abstract = work_json.get('abstract', None)
    journal = work_json.get('source', '').split('+')[0]
    if not journal:
        journal = work_json.get('journal', None)
    pub_time = parser.parse(work_json.get('date', None))
    pub_date = pub_time.strftime('%Y-%m-%d')
    pub_year = pub_time.year
    is_open_access = work_json.get('is_open_access', None)
    url = work_json.get('url', None)
    article_info = {
        'title': title,
        'doi': doi,
        'pmid': pmid,
        'pmcid': pmcid,
        'abstract': abstract,
        'journal': journal,
        'pub_date': pub_date,
        'pub_year': pub_year,
        'is_open_access': is_open_access,
        'url': url,
    }
    # ==================
    # then extract author infos:
    important_authors = []
    '''
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    orcid TEXT UNIQUE,
    h_index INTEGER,
    citations INTEGER,
    is_senior_researcher BOOLEAN,
    -- normalized_name TEXT, it seems not useful
    UNIQUE(name, orcid)
    '''
    for iauthor in work_json.get('author_details', None):
        author_name = iauthor.get('name', None)
        orcid = iauthor.get('orcid', None)
        h_index = iauthor.get('h_index', None)
        citations = iauthor.get('citations', None)
        is_senior_researcher = iauthor.get('is_senior_researcher', None)
        important_authors.append({
            'name': author_name,
            'orcid': orcid,
            'h_index': h_index,
            'citations': citations,
            'is_senior_researcher': is_senior_researcher,
        })
    # ==================
    # then extract institution infos:
    institutions_in_article = []
    """
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    raw_affiliation TEXT,
    country_name TEXT,
    """
    for iauthor in work_json.get('author_details', None):
        institute_name = iauthor.get('normalized_affiliation', None)
        country = iauthor.get('country', None)
        institutions_in_article.append({
            'name': institute_name,
            'raw_affiliation': iauthor.get('affiliation', None),
            'country_name': country,
        })
    return article_info, important_authors, institutions_in_article



def main():
    parser = argparse.ArgumentParser(description="Build SQLite database from JSONL files.")
    parser.add_argument("--jsonl", type=str, default="getfiles/all_papers_2026-03-14_enriched.jsonl",
                        help="Path to the JSONL file containing articles.")
    parser.add_argument("--db", type=str, default="data/literature.db",
                        help="Path to the output SQLite database.")
    args = parser.parse_args()
    jsonl_path = args.jsonl
    db_path = args.db   
    conn = init_db(db_path)
    countries_map_path = 'data/region.json'
    with open(countries_map_path, 'r', encoding='utf-8') as f:
        countries_map = json.load(f)

    for article_json in jsonlines.open(jsonl_path):
        article_id = insert_article(conn, article_json, countries_map)

    conn.close()

if __name__ == "__main__":
    main()