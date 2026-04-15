"""
Database Adapter - 兼容层

允许现有代码无需修改即可使用 SQLite 或 JSON 存储
"""

import os
from typing import Dict, Optional

# 设置环境变量来选择存储后端
# USE_SQLITE=true  -> 使用 SQLite
# USE_SQLITE=false -> 使用 JSON (默认)

USE_SQLITE = os.environ.get('USE_SQLITE', 'false').lower() == 'true'

if USE_SQLITE:
    print("[DB] Using SQLite backend")
    from author_database_sqlite import AuthorDatabaseSQLite, get_sqlite_db
    
    class AuthorDatabaseAdapter:
        """适配器类，提供与旧版 AuthorDatabase 相同的接口"""
        
        def __init__(self, db_path: str = "data/author_database.db"):
            self._db = AuthorDatabaseSQLite(db_path)
            self.authors = {}  # 保持兼容性
            self.institutions = {}
            self.senior_researchers = {}
        
        def load_databases(self):
            """兼容旧接口，实际数据已持久化"""
            # SQLite 数据已持久化，无需显式加载
            # 但为了兼容，填充内存字典供旧代码使用
            seniors = self._db.get_senior_researchers()
            self.senior_researchers = {s.name: s for s in seniors}
            return self
        
        def save_databases(self):
            """兼容旧接口，实际数据已自动保存"""
            # SQLite 自动提交事务，无需显式保存
            pass
        
        def update_author(self, name: str, info: Dict, paper_date: str = None):
            """更新作者"""
            self._db.update_author(name, info, paper_date)
            
            # 更新内存字典（兼容旧代码）
            self.authors[name] = info
            if info.get('is_senior_researcher'):
                self.senior_researchers[name] = info
        
        def update_institution(self, name: str, info: Dict, paper_date: str = None):
            """更新机构（简化版）"""
            # SQLite 版本暂未完全实现机构表，使用内存存储
            if name not in self.institutions:
                self.institutions[name] = {
                    'first_seen': paper_date,
                    'last_seen': paper_date,
                    'paper_count': 1,
                    **info
                }
            else:
                self.institutions[name]['last_seen'] = paper_date
                self.institutions[name]['paper_count'] += 1
                self.institutions[name].update(info)
        
        def get_author(self, name: str) -> Optional[Dict]:
            """获取作者信息"""
            info = self._db.get_author(name)
            if info:
                return {
                    'h_index': info.h_index,
                    'citations': info.citations,
                    'works_count': info.works_count,
                    'i10_index': info.i10_index,
                    'orcid': info.orcid,
                    'affiliation': info.affiliation,
                    'country': info.country,
                    'is_senior_researcher': info.is_senior_researcher,
                    'matched_name': info.matched_name,
                    'first_seen': info.first_seen,
                    'last_seen': info.last_seen,
                    'paper_count': info.paper_count,
                    'source': info.source
                }
            return None
        
        def get_statistics(self) -> Dict:
            """获取统计信息"""
            return self._db.get_statistics()
        
        def migrate_from_json(self, json_path: str = "data/author_database.json"):
            """从 JSON 迁移"""
            self._db.migrate_from_json(json_path)


    def get_database(db_path: str = "data/author_database.db"):
        """获取数据库实例"""
        db = AuthorDatabaseAdapter(db_path)
        db.load_databases()
        return db

else:
    print("[DB] Using JSON backend (set USE_SQLITE=true to use SQLite)")
    # 使用原有的 JSON 实现
    from enrich_authors import AuthorDatabase, get_database


def switch_to_sqlite(json_path: str = "data/author_database.json", 
                     db_path: str = "data/author_database.db"):
    """
    从 JSON 切换到 SQLite，并迁移数据
    
    Usage:
        from database_adapter import switch_to_sqlite
        switch_to_sqlite()
        
        # 然后设置环境变量
        import os
        os.environ['USE_SQLITE'] = 'true'
    """
    print("[DB] Migrating from JSON to SQLite...")
    db = AuthorDatabaseSQLite(db_path)
    db.migrate_from_json(json_path)
    print(f"[DB] Migration complete!")
    print(f"[DB] Now set environment variable: USE_SQLITE=true")
    return db


if __name__ == '__main__':
    # 测试适配器
    import tempfile
    import json
    
    # 创建测试 JSON
    test_json = {
        "authors": {
            "Test Author": {
                "h_index": 30,
                "citations": 5000,
                "is_senior_researcher": True,
                "first_seen": "2026-01-01",
                "last_seen": "2026-04-01"
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_json, f)
        json_path = f.name
    
    # 迁移到 SQLite
    from author_database_sqlite import AuthorDatabaseSQLite
    db_path = json_path.replace('.json', '.db')
    
    db = AuthorDatabaseSQLite(db_path)
    db.migrate_from_json(json_path)
    
    # 查询
    info = db.get_author("Test Author")
    print(f"Migrated: {info.name}, h-index: {info.h_index}")
    
    # 统计
    stats = db.get_statistics()
    print(f"Stats: {stats}")
    
    # 清理
    import os
    os.remove(json_path)
    os.remove(db_path)
