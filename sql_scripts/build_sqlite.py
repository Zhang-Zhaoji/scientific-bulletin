import json
import sqlite3
from sqlfuncs import init_db, search_item, insert_item, validate_request, search_or_insert, compare_authors
from datetime import datetime
import argparse
import os
import hashlib
import jsonlines
from dateutil import parser
import tqdm


# One example of an article in the jsonL file:
'''
{"type": "Research Article", 
"title": "Polymerase trapping as the mechanism of H5 highly pathogenic avian influenza virus genesis", 
"authors": ["Mathis Funk", 
"Monique I. Spronken", 
"Roy M. Hutchinson", 
"Benoit Arragain", 
"Pauline Juyoux", 
"Theo M. Bestebroer", 
"Anja C. M. de Bruin", 
"Alexander P. Gultyaev", 
"Ron A. M. Fouchier", 
"Stephen Cusack", 
"Aartjan J. W. te Velthuis", 
"Mathilde Richard"], 
"date": "12 Mar 2026", 
"url": "https://www.science.org/doi/10.1126/science.adr6632", 
"doi": "10.1126/science.adr6632", 
"abstract": "Highly pathogenic avian influenza viruses (HPAIVs) derive from H5 and H7 low pathogenic avian influenza viruses (LPAIVs). Although insertion of a furin-cleavable multibasic cleavage site (MBCS) in the hemagglutinin gene was identified decades ago as the genetic basis for the LPAIV-to-HPAIV transition, the mechanisms underlying the occurrence of insertion are unknown. Here, we show that transient H5 RNA structures, predicted to trap the influenza virus polymerase on purine-rich sequences, drive nucleotide insertions, providing empirical evidence of RNA structure involvement in MBCS acquisition. Introduction of H5-like sequences and structures into an H6 hemagglutinin resulted in MBCS-yielding insertions. Our results show that nucleotide insertions that underlie H5 HPAIV emergence result from an RNA structure-driven diversity-generating mechanism, which could also occur in other RNA viruses.", 
"source": "Science + Europe PMC", 
"original_source": "Science", 
"enrichment_status": "europepmc_doi", 
"pmid": "41818353", 
"pmcid": "", 
"journal": "", 
"is_open_access": false, 
"affiliations": [
"Department Of Viroscience, Erasmus University Medical Center, Rotterdam, Netherlands", 
"European Molecular Biology Laboratory, Embl Grenoble, Grenoble, France", 
"University Grenoble Alpes, Cnrs, Cea, Embl, Grenoble, France"], 
"author_details": [
{"name": "Mathis Funk", 
"h_index": 8, 
"citations": 363, 
"works_count": 26, 
"i10_index": 8, 
"orcid": "https://orcid.org/0000-0001-7830-9989", 
"is_senior_researcher": false, 
"source": "OpenAlex", 
"affiliation": ["Department of Viroscience, Erasmus University Medical Center, Rotterdam, Netherlands."], 
"normalized_affiliation": ["Department Of Viroscience, Erasmus University Medical Center, Rotterdam, Netherlands."], 
"ror_normalized_affiliation": ["Erasmus MC"], 
"ror_match_score": [100], 
"ror_country": ["The Netherlands"], 
"ror_subregion": ["South Holland"]}], 
"senior_authors": [
{"name": "Monique I. Spronken", "h_index": 24, "citations": 3093, "works_count": 53, "institution": "N/A"}, 
{"name": "Theo M. Bestebroer", "h_index": 63, "citations": 27770, "works_count": 173, "institution": "N/A"}, 
{"name": "Alexander P. Gultyaev", "h_index": 28, "citations": 2142, "works_count": 59, "institution": "N/A"}, 
{"name": "Ron A. M. Fouchier", "h_index": 125, "citations": 84710, "works_count": 634, "institution": "N/A"}, 
{"name": "Mathilde Richard", "h_index": 29, "citations": 3281, "works_count": 92, "institution": "Department Of Viroscience, Erasmus University Medical Center, Rotterdam, Netherlands."}
], 
"senior_author_names": ["Monique I. Spronken", "Theo M. Bestebroer", "Alexander P. Gultyaev", "Ron A. M. Fouchier", "Mathilde Richard"], 
"senior_author_count": 5, 
"has_senior_researcher": true, 
"countries": ["Netherlands", "France"], 
"author_enrichment_status": "enriched"}
'''

# one example of an article in the LLM JSON file:

"""
{
    "paper": {
      "raw_data": {
        "type": "Research Article",
        "title": "Polymerase trapping as the mechanism of H5 highly pathogenic avian influenza virus genesis",
        "authors": [
          "Mathis Funk",
          "Monique I. Spronken",
          "Roy M. Hutchinson",
          "Benoit Arragain",
          "Pauline Juyoux",
          "Theo M. Bestebroer",
          "Anja C. M. de Bruin",
          "Alexander P. Gultyaev",
          "Ron A. M. Fouchier",
          "Stephen Cusack",
          "Aartjan J. W. te Velthuis",
          "Mathilde Richard"
        ],
        "date": "12 Mar 2026",
        "url": "https://www.science.org/doi/10.1126/science.adr6632",
        "doi": "10.1126/science.adr6632",
        "abstract": "Highly pathogenic avian influenza viruses (HPAIVs) derive from H5 and H7 low pathogenic avian influenza viruses (LPAIVs). Although insertion of a furin-cleavable multibasic cleavage site (MBCS) in the hemagglutinin gene was identified decades ago as the genetic basis for the LPAIV-to-HPAIV transition, the mechanisms underlying the occurrence of insertion are unknown. Here, we show that transient H5 RNA structures, predicted to trap the influenza virus polymerase on purine-rich sequences, drive nucleotide insertions, providing empirical evidence of RNA structure involvement in MBCS acquisition. Introduction of H5-like sequences and structures into an H6 hemagglutinin resulted in MBCS-yielding insertions. Our results show that nucleotide insertions that underlie H5 HPAIV emergence result from an RNA structure-driven diversity-generating mechanism, which could also occur in other RNA viruses.",
        "source": "Science + Europe PMC",
        "original_source": "Science",
        "enrichment_status": "europepmc_doi",
        "pmid": "41818353",
        "pmcid": "",
        "journal": "",
        "is_open_access": false
      },
      "title": "Polymerase trapping as the mechanism of H5 highly pathogenic avian influenza virus genesis",
      "authors": [
        "Mathis Funk",
        "Monique I. Spronken",
        "Roy M. Hutchinson",
        "Benoit Arragain",
        "Pauline Juyoux",
        "Theo M. Bestebroer",
        "Anja C. M. de Bruin",
        "Alexander P. Gultyaev",
        "Ron A. M. Fouchier",
        "Stephen Cusack",
        "Aartjan J. W. te Velthuis",
        "Mathilde Richard"
      ],
      "date": "12 Mar 2026",
      "abstract": "Highly pathogenic avian influenza viruses (HPAIVs) derive from H5 and H7 low pathogenic avian influenza viruses (LPAIVs). Although insertion of a furin-cleavable multibasic cleavage site (MBCS) in the hemagglutinin gene was identified decades ago as the genetic basis for the LPAIV-to-HPAIV transition, the mechanisms underlying the occurrence of insertion are unknown. Here, we show that transient H5 RNA structures, predicted to trap the influenza virus polymerase on purine-rich sequences, drive nucleotide insertions, providing empirical evidence of RNA structure involvement in MBCS acquisition. Introduction of H5-like sequences and structures into an H6 hemagglutinin resulted in MBCS-yielding insertions. Our results show that nucleotide insertions that underlie H5 HPAIV emergence result from an RNA structure-driven diversity-generating mechanism, which could also occur in other RNA viruses.",
      "journal": "Science + Europe PMC"
    },
    "title_zh": "聚合酶捕获作为 H5 高致病性禽流感病毒起源的机制",
    "paper_id": "3d1ee66bdba2",
    "domain": "域外局限",
    "primary_category": null,
    "secondary_category": [],
    "cross_tags": [],
    "scores": {
      "Importance": 0.0,
      "Transferability": 0.0,
      "Inspiration": 0.0,
      "Timeliness": 0.0,
      "Accessibility": 0.0
    },
    "total_score": 0.0,
    "recommendation_tier": "不推送",
    "recommendation_text": "",
    "confidence": 9.8,
    "reasoning": "该研究聚焦于流感病毒的分子进化与 RNA 结构机制，属于病毒学和传染病学范畴，与神经科学无直接关联且缺乏显著的跨学科神经推论。",
    "feature_angle": "无",
    "model_used": "qwen3.5-plus",
    "key_strength": "无",
    "key_limitation": "无",
    "target_audience": "无",
    "crossover_value": "",
    "editor_note": ""
  },
"""

def parse_work_details(work_json:dict, LLM_json:dict)->tuple[dict[str, any], list[dict[str, any]], list[dict[str, any]]]:
    """
    Parse the work details from the JSON object.
    """
    # first extract article infos:
    ''' 
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        title_zh TEXT,
        doi TEXT UNIQUE,
        pmid TEXT,
        pmcid TEXT,
        abstract TEXT,
        journal TEXT,
        pub_date TEXT,
        pub_year INTEGER,
        is_open_access BOOLEAN,
        score REAL,
        url TEXT
    );
    '''
    title = work_json.get('title', None)
    title_zh = LLM_json.get('title_zh', None)
    doi = work_json.get('doi', None)
    pmid = work_json.get('pmid', None)
    pmcid = work_json.get('pmcid', None)
    abstract = work_json.get('abstract', None)
    journal = work_json.get('source', '').split('+')[0]
    if not journal:
        journal = work_json.get('journal', None)
    date_str = work_json.get('date', None)
    if date_str and date_str.strip():
        pub_time = parser.parse(date_str)
        pub_date = pub_time.strftime('%Y-%m-%d')
        pub_year = pub_time.year
    else:
        pub_date = None
        pub_year = None
    is_open_access = work_json.get('is_open_access', None)
    score = LLM_json.get('total_score', None)
    url = work_json.get('url', None)
    article_info = {
        'title': title,
        'title_zh': title_zh,
        'doi': doi,
        'pmid': pmid,
        'pmcid': pmcid,
        'abstract': abstract,
        'journal': journal,
        'pub_date': pub_date,
        'pub_year': pub_year,
        'is_open_access': is_open_access,
        'score': score,
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
    author_details = work_json.get('author_details', None)
    if author_details:
        for iauthor in author_details:
            author_name = iauthor.get('name', None)
            orcid = iauthor.get('orcid', None)
            h_index = iauthor.get('h_index', None)
            citations = iauthor.get('citations', None)
            is_senior_researcher = iauthor.get('is_senior_researcher', None)
            # add institute_name for further check
            # 优先使用 ROR 标准化的机构名称
            institute_names = iauthor.get('ror_normalized_affiliation', None)
            if not institute_names:
                institute_names = iauthor.get('normalized_affiliation', None)
            if isinstance(institute_names, str):
                institute_names = institute_names.split(';') # default to be a list
            important_authors.append({
                'name': author_name,
                'orcid': orcid,
                'h_index': h_index,
                'citations': citations,
                'is_senior_researcher': is_senior_researcher,
                'institute_name': institute_names,
                })
    # ==================
    # then extract institution infos:
    institutions_in_article = []
    """
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    raw_affiliation TEXT,
    country_name TEXT,
    normalized_name TEXT UNIQUE,
    """
    author_details = work_json.get('author_details', None)
    if author_details:
        for iauthor in author_details:
            institute_name = iauthor.get('normalized_affiliation', None)
            if not institute_name:
                continue
            if isinstance(institute_name, str):
                institute_name = institute_name.split(';') # default to be a list
            institute_name = [i.strip() for i in institute_name]
            country = iauthor.get('ror_country', iauthor.get('country', [None]))
            if isinstance(country, str):
                country = country.strip()
                country = [country] * len(institute_name) if institute_name else [None]
            if country and isinstance(country, list) and len(country) > 0 and isinstance(country[0], list):
                country = country[0]
            # the above lines should be ensured during the enrichment process
            score = iauthor.get('score', 0)
            institutions_in_article.append({
                'name': iauthor.get('ror_normalized_affiliation', None) if iauthor.get('ror_normalized_affiliation', None) else institute_name,
                'raw_affiliation': iauthor.get('affiliation', None), # original_affiliation string
                'country_name': country,
                'normalized_name': iauthor.get('ror_normalized_affiliation', None),
                })
    # finally, theme infos:
    """
    -- 主题表
    CREATE TABLE IF NOT EXISTS themes (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );

    -- 子主题表
    CREATE TABLE IF NOT EXISTS subthemes (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    """
    themes = []
    subthemes = []
    crosstags = []
    if LLM_json.get('domain', None) == "域外局限":
        themes.append({
            'name': '域外局限',
        })
    elif LLM_json.get('domain', None) == "核心域":
        themes.append({
            'name': LLM_json.get('primary_category', None),
        })
        for sub_theme in LLM_json.get('secondary_categories', []):
            subthemes.append({
                'name': sub_theme,
            })
        for tag in LLM_json.get('cross_tags', []):
            crosstags.append({
                'name': tag,
            })
    elif LLM_json.get('domain', None) == "域外高影响":
        themes.append({
            'name': '域外高影响',
        })
        for sub_theme in LLM_json.get('secondary_category', []):
            subthemes.append({
                'name': sub_theme,
            })
        for tag in LLM_json.get('cross_tags', []):
            crosstags.append({
                'name': tag,
            })
    else:
        raise ValueError(f"Unknown domain: {LLM_json.get('domain', None)}")
    return article_info, important_authors, institutions_in_article, themes, subthemes, crosstags


def insert_article_info(conn, article_info, important_authors, institutions_in_article, themes, subthemes, crosstags):
    """
    Insert the article into the database.
    """
    table_names = ['countries', 'articles', 'authors', 'institutions', 'themes', 'subthemes', 'crosstags', 'author_institutions', 'article_authors', 'article_institutions', 'article_themes', 'article_subthemes', 'article_crosstags']
    
    table_keys = {'countries': ['country_name','standard_name'],
                  'articles': ['title','title_zh', 'doi', 'pmid', 'pmcid', 'abstract', 'journal', 'pub_date', 'pub_year', 'is_open_access', 'score', 'url'], 
                  'authors': ['name', 'orcid', 'h_index', 'citations', 'is_senior_researcher'], 
                  'institutions': ['name', 'raw_affiliation', 'country_id', 'normalized_name'], 
                  'themes': ['name'],
                  'subthemes': ['name'],
                  'crosstags': ['name'],
                  'author_institutions': ['author_id', 'institution_id'],
                  'article_authors': ['article_id', 'author_id'], 
                  'article_institutions': ['article_id', 'institution_id'], 
                  'article_themes': ['article_id', 'theme_id'],
                  'article_subthemes': ['article_id', 'subtheme_id'],
                  'article_crosstags': ['article_id', 'tag_id']}

    conflict_keys = {'countries': ['standard_name'],
                     'articles': ['title'], 
                     'authors': ['orcid'], 
                     'institutions': ['name'], 
                     'themes': ['name'],
                     'subthemes': ['name'],
                     'crosstags': ['name'],
                     'author_institutions': ['author_id', 'institution_id'],
                     'article_authors': ['article_id', 'author_id'], 
                     'article_institutions': ['article_id', 'institution_id'], 
                     'article_themes': ['article_id', 'theme_id'],
                     'article_subthemes': ['article_id', 'subtheme_id'],
                     'article_crosstags': ['article_id', 'tag_id']}
    
    article_id = search_or_insert(conn, 'articles', conflict_keys['articles'], article_info)
    
    all_institution_ids = []
    for inst in institutions_in_article:
        institute_names = inst['name']
        country_names = inst.get('country_name', [])
        normalized_names = inst.get('normalized_name', [])
        raw_affiliation = inst.get('raw_affiliation',[])
        
        if not isinstance(institute_names, list):
            institute_names = [institute_names]
        if not isinstance(country_names, list):
            country_names = [country_names]
        if not isinstance(normalized_names, list):
            normalized_names = [normalized_names]
        
        if len(country_names) < len(institute_names):
            country_names.extend([None] * (len(institute_names) - len(country_names)))
        
        for institute_name, country_name, normalized_name in zip(institute_names, country_names, normalized_names):
            if not institute_name:
                continue
            
            country_id = None
            if country_name:
                cursor = conn.execute("SELECT id FROM countries WHERE standard_name = ?", (country_name,))
                result = cursor.fetchone()
                if result:
                    country_id = result[0]
                else:
                    raise ValueError(f"Country {country_name} not found in database database.")
            inst_data = {
                'name': institute_name,
                'raw_affiliation': raw_affiliation,
                'country_id': country_id,
                'normalized_name': normalized_name,
            }
            institution_id = search_or_insert(conn, 'institutions', conflict_keys['institutions'], inst_data)
            all_institution_ids.append(institution_id)
            
            search_or_insert(conn, 'article_institutions', conflict_keys['article_institutions'],
                            {'article_id': article_id, 'institution_id': institution_id})
    
    author_ids = []
    for author in important_authors:
        institute_names = author.get('institute_name', [])
        if not isinstance(institute_names, list):
            institute_names = [institute_names]
        
        current_institution_ids = []
        for institute_name in institute_names:
            if not institute_name:
                continue
            # 先尝试使用原始名称搜索
            found_ids = search_item(conn, 'institutions', ['name'], [institute_name])
            if found_ids:
                current_institution_ids.extend(found_ids)
            else:
                # 如果没找到，尝试使用 normalized_name 搜索
                found_ids = search_item(conn, 'institutions', ['normalized_name'], [institute_name])
                if found_ids:
                    current_institution_ids.extend(found_ids)
                else:
                    # 尝试模糊搜索
                    cursor = conn.execute("SELECT id FROM institutions WHERE name LIKE ? OR normalized_name LIKE ?", (f"%{institute_name}%", f"%{institute_name}%"))
                    result = cursor.fetchall()
                    if result:
                        current_institution_ids.extend([row[0] for row in result])
        
        candidate_ids = search_item(conn, 'authors', ['name'], [author['name']])
        matched_id = None
        if candidate_ids:
            matched_id = compare_authors(conn, author, candidate_ids)
        
        if matched_id:
            author_id = matched_id
        else:
            author_data = {k: v for k, v in author.items() if k in table_keys['authors']}
            author_id = search_or_insert(conn, 'authors', conflict_keys['authors'], author_data)
        author_ids.append(author_id)
        
        for institution_id in current_institution_ids:
            search_or_insert(conn, 'author_institutions', conflict_keys['author_institutions'],
                            {'author_id': author_id, 'institution_id': institution_id})
    
    for theme in themes:
        theme_id = search_or_insert(conn, 'themes', conflict_keys['themes'], theme)
        search_or_insert(conn, 'article_themes', conflict_keys['article_themes'],
                        {'article_id': article_id, 'theme_id': theme_id})
    
    for subtheme in subthemes:
        subtheme_id = search_or_insert(conn, 'subthemes', conflict_keys['subthemes'], subtheme)
        search_or_insert(conn, 'article_subthemes', conflict_keys['article_subthemes'],
                        {'article_id': article_id, 'subtheme_id': subtheme_id})
    
    for tag in crosstags:
        tag_id = search_or_insert(conn, 'crosstags', conflict_keys['crosstags'], tag)
        search_or_insert(conn, 'article_crosstags', conflict_keys['article_crosstags'],
                        {'article_id': article_id, 'tag_id': tag_id})
    
    for author_id in author_ids:
        search_or_insert(conn, 'article_authors', conflict_keys['article_authors'],
                        {'article_id': article_id, 'author_id': author_id})


def main():
    DB_PATH="data/literature.db"
    parser = argparse.ArgumentParser(description="Build SQLite database from JSONL files.")
    parser.add_argument("--jsonl", type=str, default="getfiles/all_papers_2026-04-18_enriched_ror_refined_new.jsonl",
                        help="Path to the JSONL file containing articles.")
    parser.add_argument("--LLM_results", type=str, default="LLM_Results/LLM_results_20260418_023838.json",
                        help="Path to the JSON file containing LLM feedback results.")
    args = parser.parse_args()
    jsonl_path = args.jsonl
    LLM_results_path = args.LLM_results
    conn = init_db(DB_PATH)

    countries_list_path = 'data/CountryList.json'
    alias_country_path = 'data/aliasCountryName.json'
    abbr2country_path = 'data/abbr2country.json'
    with open(alias_country_path, 'r', encoding='utf-8') as f:
        alias_country = json.load(f)
    with open(countries_list_path, 'r', encoding='utf-8') as f:
        countries_list = json.load(f)
    with open(abbr2country_path, 'r', encoding='utf-8') as f:
        abbr2country = json.load(f)
    all_country_names = countries_list + list(alias_country.values()) + list(abbr2country.values())
    all_country_names = list(set(all_country_names))
    
    for country_name in all_country_names:
        country_data = {
            'country_name': country_name,
            'standard_name': country_name
        }
        search_or_insert(conn, 'countries', ['standard_name'], country_data)
    
    with open(LLM_results_path, 'r', encoding='utf-8') as f:
        LLM_results = json.load(f)

    for article_json, LLM_json in tqdm.tqdm(zip(jsonlines.open(jsonl_path), LLM_results)):
        # 0. check the title matches
        assert article_json.get('title') is not None, "Article title is None"
        assert article_json.get('title').replace(' ', '').replace('\n', '') == LLM_json.get('paper').get('raw_data').get('title').replace(' ', '').replace('\n', ''), f"Article title in JSONL and LLM do not match: \n{article_json.get('title')} != \n{LLM_json.get('paper').get('raw_data').get('title')}"
        # 1. parse the article details
        article_info, important_authors, institutions_in_article, themes, subthemes, crosstags = parse_work_details(article_json, LLM_json)
        # 2. insert the article into the database
        insert_article_info(conn, article_info, important_authors, institutions_in_article, themes, subthemes, crosstags)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    
    main()