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

def parse_work_details(work_json:dict)->tuple[dict[str, any], list[dict[str, any]], list[dict[str, any]]]:
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
        # add institute_name for further check
        institute_name = iauthor.get('normalized_affiliation', None)
        if isinstance(institute_name, str):
            institute_name = institute_name.split(';') # default to be a list
        important_authors.append({
            'name': author_name,
            'orcid': orcid,
            'h_index': h_index,
            'citations': citations,
            'is_senior_researcher': is_senior_researcher,
            'institute_name': institute_name,
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
        if isinstance(institute_name, str):
            institute_name = institute_name.split(';') # default to be a list
        country = iauthor.get('country', None)
        if isinstance(country, str):
            country = country.split(';') # default to be a list, too
        # the above lines should be ensured during the enrichment process
        institutions_in_article.append({
            'name': institute_name,
            'raw_affiliation': iauthor.get('affiliation', None), # original_affiliation string
            'country_name': country,
        })
    return article_info, important_authors, institutions_in_article


def validate_request(table_name: str, conflict_columns: list[str], insert_data: dict[str, any]) -> None:
    """
    Validate the request parameters.
    """
    if not table_name.isidentifier():
        raise ValueError("表名必须为合法的 SQL 标识符")
    for col in conflict_columns:
        if not col.isidentifier():
            raise ValueError("冲突列名必须为合法的 SQL 标识符")
    for col in insert_data.keys():
        if not col.isidentifier():
            raise ValueError("插入列名必须为合法的 SQL 标识符")

def search_item(conn, table_name: str, columns: list[str], values: list[any]) -> list[int]:
    """
    Search for an item in the database by multiple columns, return the potential ids.
    """
    query = f"""
        SELECT id FROM {table_name} 
        WHERE {', '.join([f"{col} = ?" for col in columns])};
    """
    values = values
    cursor = conn.execute(query, values)
    result = cursor.fetchall()
    if result:
        return [row[0] for row in result]
    return None

def insert_item(conn, table_name: str, columns: list[str], values: list[any]) -> int:
    """
    Insert an item into the database, and return the inserted id.
    """
    placeholders = ', '.join(['?' for _ in columns])
    columns_str = ', '.join(columns)
    query = f"""
        INSERT INTO {table_name} ({columns_str}) 
        VALUES ({placeholders}) 
        RETURNING id;
    """
    cursor = conn.execute(query, values)
    conn.commit()
    result = cursor.fetchone()
    return result[0]

def compare_authors(conn, author: dict, conflict_author_ids: list[int]) -> int|None:
    """
    Compare authors with institutions.
    匹配规则：
    1. 如果 orcid 存在且相同，直接返回匹配的 id
    2. 检查每个候选作者已关联的 institutions，如果和当前作者的 institutions 有交集，返回匹配的 id
    3. 没有匹配返回 None
    """
    author_orcid = author.get('orcid')
    
    if author_orcid:
        placeholders = ', '.join(['?' for _ in conflict_author_ids])
        query = f"""
            SELECT id FROM authors 
            WHERE id IN ({placeholders}) AND orcid = ?
            LIMIT 1;
        """
        cursor = conn.execute(query, (*conflict_author_ids, author_orcid))
        result = cursor.fetchall()
        if result:
            assert len(result) == 1, f"orcid {author_orcid} 匹配到多个作者"
            return result[0][0]
    
    institutions: list[str] = author.get('institute_name', None)
    if isinstance(institutions, str):
        institutions = institutions.split(';')
    if not institutions:
        return None
    
    existing_institution_ids = []
    for institution in institutions:
        found = search_item(conn, 'institutions', ['name'], [institution])
        if found:
            existing_institution_ids.extend(found)
    if not existing_institution_ids:
        return None
    
    existing_institution_set = set(existing_institution_ids)
    for candidate_id in conflict_author_ids:
        cursor = conn.execute("""
            SELECT DISTINCT institution_id 
            FROM author_institutions 
            WHERE author_id = ?
        """, (candidate_id,))
        candidate_institutions = set(row[0] for row in cursor.fetchall())
        if candidate_institutions & existing_institution_set:
            return candidate_id
    return None


def search_or_insert(conn, table_name: str, conflict_columns: list[str], insert_data: dict[str, any]) -> int:
    validate_request(table_name, conflict_columns, insert_data)
    conflict_values = [insert_data[col] for col in conflict_columns]
    existing_ids = search_item(conn, table_name, conflict_columns, conflict_values)
    if existing_ids is not None:
        if table_name in ['countries', 'articles', 'institutions', 'themes', 'author_institutions', 'article_authors', 'article_institutions', 'article_themes']:
            assert len(existing_ids) == 1
            return existing_ids[0]
        elif table_name == 'authors':
            precise_compare_id = compare_authors(conn, insert_data, existing_ids)
            if precise_compare_id is not None:
                return precise_compare_id
        else: # ERROR!
            raise ValueError(f"表名 {table_name} 不支持直接返回已存在 id")
    insert_columns = list(insert_data.keys())
    values = list(insert_data.values())
    result = insert_item(conn, table_name, insert_columns, values)
    return result

def process_one_article(conn, article_json):
    """
    Insert the article into the database.
    """
    article_info, important_authors, institutions_in_article = parse_work_details(article_json)
    table_names = ['countries', 'articles', 'authors', 'institutions', 'themes', 'author_institutions', 'article_authors', 'article_institutions', 'article_themes']
    
    table_keys = {'countries': ['en_name', 'ch_name','iso_code','conutry_name','standard_name'],
                  'articles': ['title', 'doi', 'pmid', 'pmcid', 'abstract', 'journal', 'pub_date', 'pub_year', 'is_open_access', 'url'], 
                  'authors': ['name', 'orcid', 'h_index', 'citations', 'is_senior_researcher'], 
                  'institutions': ['name', 'raw_affiliation', 'country_id'], 
                  'themes': ['name'],
                  'author_institutions': ['author_id', 'institution_id'],
                  'article_authors': ['article_id', 'author_id'], 
                  'article_institutions': ['article_id', 'institution_id'], 
                  'article_themes': ['article_id', 'theme_id']}

    conflict_keys = {'countries': ['standard_name'],
                     'articles': ['title'], 
                     'authors': ['name'], 
                     'institutions': ['name'], 
                     'themes': ['name'],
                     'author_institutions': ['author_id', 'institution_id'],
                     'article_authors': ['article_id', 'author_id'], 
                     'article_institutions': ['article_id', 'institution_id'], 
                     'article_themes': ['article_id', 'theme_id']}
    
    # first get countries, if the country is not in the database, then insert it
    country_name = article_info['country_name']


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
        process_one_article(conn, article_json, countries_map)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()