import sqlite3
import os

DB_PATH = '../data/literature.db'

if not os.path.exists(DB_PATH):
    DB_PATH = 'data/literature.db'

class DBAPI:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
    
    def close(self):
        self.conn.close()
    
    def get_country_article_count(self, start_date=None, end_date=None)->list[tuple[str, int]]:
        """
        查询每个国家在给定日期范围内的文章数量
        :param start_date: 起始日期 (YYYY-MM-DD)，None 表示不限制
        :param end_date: 结束日期 (YYYY-MM-DD)，None 表示不限制
        :return: [(国家标准名称, 文章数量), ...]
        """
        query = """
        SELECT c.standard_name, COUNT(DISTINCT a.id) as article_count
        FROM countries c
        JOIN institutions i ON c.id = i.country_id
        JOIN article_institutions ai ON i.id = ai.institution_id
        JOIN articles a ON ai.article_id = a.id
        WHERE a.id NOT IN (SELECT article_id FROM article_themes WHERE theme_id = 1)
        """
        params = []
        
        if start_date:
            query += " AND a.pub_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND a.pub_date <= ?"
            params.append(end_date)
        
        query += """
        GROUP BY c.id, c.standard_name
        ORDER BY article_count DESC
        """
        
        self.cursor.execute(query, params)
        results = self.cursor.fetchall()
        
        return [(row[0], row[1]) for row in results]