"""
SQLite-based Author Database

替代 JSON 文件存储，提供：
- 事务安全（并发不会损坏）
- SQL查询（快速筛选）
- 自动索引（快速查找）
- 零配置（单文件）
"""

import sqlite3
import json
import os
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass
from contextlib import contextmanager


@dataclass
class AuthorInfo:
    """作者信息"""
    name: str
    h_index: Optional[int] = None
    citations: Optional[int] = None
    works_count: Optional[int] = None
    i10_index: Optional[int] = None
    orcid: Optional[str] = None
    affiliation: Optional[str] = None
    country: Optional[str] = None
    is_senior_researcher: bool = False
    matched_name: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    paper_count: int = 0
    source: str = "Unknown"


class AuthorDatabaseSQLite:
    """
    SQLite 作者数据库
    
    Usage:
        db = AuthorDatabaseSQLite("data/authors.db")
        
        # 更新作者
        db.update_author("John Doe", {"h_index": 30, "citations": 5000}, "2026-04-01")
        
        # 查询作者
        info = db.get_author("John Doe")
        
        # 获取所有大牛
        seniors = db.get_senior_researchers(min_h_index=25)
        
        # 获取统计
        stats = db.get_statistics()
    """
    
    def __init__(self, db_path: str = "data/author_database.db"):
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()
    
    def _ensure_dir(self):
        """确保目录存在"""
        dir_path = os.path.dirname(self.db_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    @contextmanager
    def _get_conn(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 让结果可以通过列名访问
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # 作者表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    h_index INTEGER,
                    citations INTEGER,
                    works_count INTEGER,
                    i10_index INTEGER,
                    orcid TEXT,
                    affiliation TEXT,
                    country TEXT,
                    is_senior_researcher BOOLEAN DEFAULT 0,
                    matched_name TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    paper_count INTEGER DEFAULT 0,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 机构表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS institutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    country TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    paper_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 作者-机构关联表（多对多）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS author_institutions (
                    author_id INTEGER,
                    institution_id INTEGER,
                    first_seen TEXT,
                    last_seen TEXT,
                    PRIMARY KEY (author_id, institution_id),
                    FOREIGN KEY (author_id) REFERENCES authors(id),
                    FOREIGN KEY (institution_id) REFERENCES institutions(id)
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_authors_h_index ON authors(h_index)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_authors_senior ON authors(is_senior_researcher)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_institutions_name ON institutions(name)")
            
            conn.commit()
            print(f"[DB] Initialized SQLite database: {self.db_path}")
    
    def update_author(self, name: str, info: Dict, paper_date: str = None):
        """
        更新或插入作者信息
        
        Args:
            name: 作者名
            info: 作者信息字典
            paper_date: 论文日期 (YYYY-MM-DD)
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # 检查是否已存在
            cursor.execute("SELECT * FROM authors WHERE name = ?", (name,))
            existing = cursor.fetchone()
            
            now = datetime.now().isoformat()
            
            if existing:
                # 更新现有记录
                # 只更新非空值，保留已有信息
                updates = []
                params = []
                
                if info.get('h_index') is not None:
                    updates.append("h_index = ?")
                    params.append(info['h_index'])
                if info.get('citations') is not None:
                    updates.append("citations = ?")
                    params.append(info['citations'])
                if info.get('works_count') is not None:
                    updates.append("works_count = ?")
                    params.append(info['works_count'])
                if info.get('i10_index') is not None:
                    updates.append("i10_index = ?")
                    params.append(info['i10_index'])
                if info.get('orcid') is not None:
                    updates.append("orcid = ?")
                    params.append(info['orcid'])
                if info.get('affiliation') is not None:
                    updates.append("affiliation = ?")
                    params.append(info['affiliation'])
                if info.get('country') is not None:
                    updates.append("country = ?")
                    params.append(info['country'])
                if info.get('is_senior_researcher') is not None:
                    updates.append("is_senior_researcher = ?")
                    params.append(1 if info['is_senior_researcher'] else 0)
                if info.get('matched_name') is not None:
                    updates.append("matched_name = ?")
                    params.append(info['matched_name'])
                if info.get('source') is not None:
                    updates.append("source = ?")
                    params.append(info['source'])
                
                # 更新时间
                updates.append("updated_at = ?")
                params.append(now)
                
                # 更新 last_seen
                if paper_date:
                    updates.append("last_seen = ?")
                    params.append(paper_date)
                
                # 增加论文计数
                updates.append("paper_count = paper_count + 1")
                
                if updates:
                    params.append(name)
                    sql = f"UPDATE authors SET {', '.join(updates)} WHERE name = ?"
                    cursor.execute(sql, params)
            else:
                # 插入新记录
                cursor.execute("""
                    INSERT INTO authors 
                    (name, h_index, citations, works_count, i10_index, orcid, 
                     affiliation, country, is_senior_researcher, matched_name,
                     first_seen, last_seen, source, paper_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    name,
                    info.get('h_index'),
                    info.get('citations'),
                    info.get('works_count'),
                    info.get('i10_index'),
                    info.get('orcid'),
                    info.get('affiliation'),
                    info.get('country'),
                    1 if info.get('is_senior_researcher') else 0,
                    info.get('matched_name'),
                    paper_date,
                    paper_date,
                    info.get('source', 'Unknown')
                ))
    
    def get_author(self, name: str) -> Optional[AuthorInfo]:
        """获取作者信息"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM authors WHERE name = ?", (name,))
            row = cursor.fetchone()
            
            if row:
                return AuthorInfo(
                    name=row['name'],
                    h_index=row['h_index'],
                    citations=row['citations'],
                    works_count=row['works_count'],
                    i10_index=row['i10_index'],
                    orcid=row['orcid'],
                    affiliation=row['affiliation'],
                    country=row['country'],
                    is_senior_researcher=bool(row['is_senior_researcher']),
                    matched_name=row['matched_name'],
                    first_seen=row['first_seen'],
                    last_seen=row['last_seen'],
                    paper_count=row['paper_count'],
                    source=row['source']
                )
            return None
    
    def get_senior_researchers(self, min_h_index: int = 25) -> List[AuthorInfo]:
        """获取所有大牛作者"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM authors 
                WHERE is_senior_researcher = 1 OR h_index >= ?
                ORDER BY h_index DESC
            """, (min_h_index,))
            
            rows = cursor.fetchall()
            return [AuthorInfo(
                name=row['name'],
                h_index=row['h_index'],
                citations=row['citations'],
                works_count=row['works_count'],
                i10_index=row['i10_index'],
                orcid=row['orcid'],
                affiliation=row['affiliation'],
                country=row['country'],
                is_senior_researcher=bool(row['is_senior_researcher']),
                matched_name=row['matched_name'],
                first_seen=row['first_seen'],
                last_seen=row['last_seen'],
                paper_count=row['paper_count'],
                source=row['source']
            ) for row in rows]
    
    def search_authors(self, query: str, limit: int = 20) -> List[AuthorInfo]:
        """搜索作者（模糊匹配）"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM authors 
                WHERE name LIKE ? OR matched_name LIKE ?
                ORDER BY h_index DESC NULLS LAST
                LIMIT ?
            """, (f'%{query}%', f'%{query}%', limit))
            
            rows = cursor.fetchall()
            return [AuthorInfo(
                name=row['name'],
                h_index=row['h_index'],
                citations=row['citations'],
                is_senior_researcher=bool(row['is_senior_researcher'])
            ) for row in rows]
    
    def get_statistics(self) -> Dict:
        """获取数据库统计信息"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # 总作者数
            cursor.execute("SELECT COUNT(*) FROM authors")
            total_authors = cursor.fetchone()[0]
            
            # 大牛数
            cursor.execute("SELECT COUNT(*) FROM authors WHERE is_senior_researcher = 1")
            senior_count = cursor.fetchone()[0]
            
            # 有h-index的作者
            cursor.execute("SELECT COUNT(*) FROM authors WHERE h_index IS NOT NULL")
            with_metrics = cursor.fetchone()[0]
            
            # 平均h-index
            cursor.execute("SELECT AVG(h_index) FROM authors WHERE h_index IS NOT NULL")
            avg_h_index = cursor.fetchone()[0] or 0
            
            # 最高h-index
            cursor.execute("SELECT MAX(h_index) FROM authors")
            max_h_index = cursor.fetchone()[0] or 0
            
            # 机构数
            cursor.execute("SELECT COUNT(*) FROM institutions")
            institution_count = cursor.fetchone()[0]
            
            return {
                'total_authors': total_authors,
                'senior_researchers': senior_count,
                'authors_with_metrics': with_metrics,
                'avg_h_index': round(avg_h_index, 2),
                'max_h_index': max_h_index,
                'institutions': institution_count
            }
    
    def get_top_authors(self, n: int = 20) -> List[AuthorInfo]:
        """获取h-index最高的作者"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM authors 
                WHERE h_index IS NOT NULL
                ORDER BY h_index DESC
                LIMIT ?
            """, (n,))
            
            rows = cursor.fetchall()
            return [AuthorInfo(
                name=row['name'],
                h_index=row['h_index'],
                citations=row['citations'],
                works_count=row['works_count'],
                is_senior_researcher=bool(row['is_senior_researcher'])
            ) for row in rows]
    
    def migrate_from_json(self, json_path: str = "data/author_database.json"):
        """从旧版 JSON 迁移数据"""
        if not os.path.exists(json_path):
            print(f"[DB] JSON file not found: {json_path}")
            return
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        authors = data.get('authors', {})
        print(f"[DB] Migrating {len(authors)} authors from JSON to SQLite...")
        
        count = 0
        for name, info in authors.items():
            self.update_author(name, info, info.get('last_seen'))
            count += 1
            if count % 100 == 0:
                print(f"  ... migrated {count}/{len(authors)}")
        
        print(f"[DB] Migration complete: {count} authors")
    
    def export_to_json(self, output_path: str = None):
        """导出为 JSON（备份用）"""
        if output_path is None:
            output_path = f"data/author_database_backup_{datetime.now().strftime('%Y%m%d')}.json"
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM authors")
            rows = cursor.fetchall()
            
            data = {
                'authors': {},
                'export_date': datetime.now().isoformat(),
                'count': len(rows)
            }
            
            for row in rows:
                data['authors'][row['name']] = {
                    'h_index': row['h_index'],
                    'citations': row['citations'],
                    'works_count': row['works_count'],
                    'i10_index': row['i10_index'],
                    'orcid': row['orcid'],
                    'affiliation': row['affiliation'],
                    'country': row['country'],
                    'is_senior_researcher': bool(row['is_senior_researcher']),
                    'matched_name': row['matched_name'],
                    'first_seen': row['first_seen'],
                    'last_seen': row['last_seen'],
                    'paper_count': row['paper_count'],
                    'source': row['source']
                }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[DB] Exported to {output_path}")
        return output_path


# 全局实例（单例模式）
_db_instance = None

def get_sqlite_db(db_path: str = "data/author_database.db") -> AuthorDatabaseSQLite:
    """获取全局数据库实例"""
    global _db_instance
    if _db_instance is None or _db_instance.db_path != db_path:
        _db_instance = AuthorDatabaseSQLite(db_path)
    return _db_instance


if __name__ == '__main__':
    # 测试
    db = AuthorDatabaseSQLite("test.db")
    
    # 插入测试数据
    db.update_author("Test Author", {
        'h_index': 30,
        'citations': 5000,
        'is_senior_researcher': True
    }, "2026-04-01")
    
    # 查询
    info = db.get_author("Test Author")
    print(f"Author: {info.name}, h-index: {info.h_index}")
    
    # 统计
    stats = db.get_statistics()
    print(f"Stats: {stats}")
    
    # 清理
    os.remove("test.db")
