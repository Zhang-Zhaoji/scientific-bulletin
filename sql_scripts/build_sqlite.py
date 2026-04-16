import json
import sqlite3
from datetime import datetime
import argparse
import os
import hashlib
import jsonlines

def init_db(db_path="data/literature.db"):
    conn = sqlite3.connect(db_path)
    conn.executescript(open('sql_scripts/schema.sql', 'r', encoding='utf-8').read())
    return conn

def extract_country_from_normalized_aff(aff: str, countries_map: dict):
    """
    针对已标准化的机构名：国家通常在最后，用逗号分隔
    如 "..., Rotterdam, Netherlands" -> 匹配 Netherlands
    """
    if not aff:
        return None
    
    # 按逗号分割，从后向前检查
    parts = [p.strip() for p in aff.split(',')]
    
    for part in reversed(parts):
        part_clean = part.rstrip('.').lower()  # 去掉末尾句点
        for country_en, cid in countries_map.items():
            if part_clean == country_en.lower():
                return (country_en, cid, aff)
            # 也检查 ch_name（如果你的 countries_map 包含中文）
    
    return None  # 未找到

def insert_article(conn, article_json: dict, countries_map: dict):
    """
    article_json: 你附件那样的文献JSON
    countries_map: 国家名到id的映射（从你的政权JSON构建）
    """
    cur = conn.cursor()
    
    # 1. 插入文章主表
    cur.execute("""
        INSERT OR REPLACE INTO articles 
        (doi, pmid, pmcid, title, abstract, journal, pub_date, pub_year, 
         source, is_open_access, url, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        article_json.get("doi"),
        article_json.get("pmid"),
        article_json.get("pmcid"),
        article_json.get("title"),
        article_json.get("abstract"),
        article_json.get("journal"),
        article_json.get("date"),
        int(article_json.get("date")[-4:]) if article_json.get("date") else None,
        article_json.get("source"),
        article_json.get("is_open_access"),
        article_json.get("url"),
        json.dumps(article_json, ensure_ascii=False)
    ))
    article_id = cur.lastrowid or cur.execute(
        "SELECT id FROM articles WHERE doi=?", (article_json["doi"],)
    ).fetchone()[0]
    
    # 2. 处理作者（去重插入 + 关联）
    senior_names = set(article_json.get("senior_author_names", []))
    for idx, author in enumerate(article_json.get("author_details", [])):
        
        # ... 插入/获取 author_id 的代码 ...
        author_id = author.get("https://orcid.org/0000-0001-7830-9989", None)
        # 3. 处理机构（支持多机构）
        aff = author.get("normalized_affiliation") or author.get("affiliation", "")
        
        # 提取所有国家匹配
        country_matches = extract_country_from_normalized_aff(aff, countries_map)
        
        if country_matches:
            # 有匹配到国家的机构
            print(country_matches)
            input("Press Enter to continue...")
            
            for country_en, cid, segment in [country_matches]:
                cid = hashlib.md5(cid['en_name'].encode()).hexdigest()
                # 用原始片段作为机构名（或进一步清洗）
                inst_name = segment.strip()
                
                cur.execute("""
                    INSERT OR IGNORE INTO institutions 
                    (name, normalized_name, country_id, raw_affiliation)
                    VALUES (?, ?, ?, ?)
                """, (inst_name, inst_name, cid, aff))
                
                inst_id = cur.execute(
                    "SELECT id FROM institutions WHERE name=? AND country_id=?", 
                    (inst_name, cid)
                ).fetchone()[0]
                
                cur.execute("""
                    INSERT OR IGNORE INTO article_institutions 
                    (article_id, institution_id, author_id)
                    VALUES (?, ?, ?)
                """, (article_id, inst_id, author_id))
        else:
            # 未匹配到任何国家，仍然记录但 country_id 为 NULL
            cur.execute("""
                INSERT OR IGNORE INTO institutions 
                (name, normalized_name, country_id, raw_affiliation)
                VALUES (?, ?, ?, ?)
            """, (aff, aff, None, aff))
            
            inst_id = cur.execute(
                "SELECT id FROM institutions WHERE normalized_name=? AND country_id IS NULL", 
                (aff,)
            ).fetchone()
            
            if inst_id:  # 确保有返回
                cur.execute("""
                    INSERT OR IGNORE INTO institutions 
                    (article_id, id, author_id)
                    VALUES (?, ?, ?)
                """, (article_id, inst_id[0], author_id))
    conn.commit()
    return article_id

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