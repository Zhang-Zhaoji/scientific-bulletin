#!/usr/bin/env python3
"""
一键迁移脚本：从 JSON 迁移到 SQLite

Usage:
    python migrate_to_sqlite.py
    
环境变量:
    DRY_RUN=true    # 只测试，不实际写入
"""

import os
import sys

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from author_database_sqlite import AuthorDatabaseSQLite

def migrate():
    json_path = "data/author_database.json"
    db_path = "data/author_database.db"
    
    print("=" * 80)
    print("Author Database Migration Tool")
    print("=" * 80)
    
    # 检查 JSON 文件
    if not os.path.exists(json_path):
        print(f"[ERROR] JSON file not found: {json_path}")
        print("[INFO] Nothing to migrate")
        return
    
    print(f"Source: {json_path}")
    print(f"Target: {db_path}")
    
    dry_run = os.environ.get('DRY_RUN', '').lower() == 'true'
    if dry_run:
        print("\n[DRY RUN] No actual changes will be made")
    
    # 加载 JSON 查看大小
    import json
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    authors_count = len(data.get('authors', {}))
    institutions_count = len(data.get('institutions', {}))
    
    print(f"\nData to migrate:")
    print(f"  - Authors: {authors_count}")
    print(f"  - Institutions: {institutions_count}")
    
    if authors_count == 0:
        print("\n[INFO] No authors to migrate")
        return
    
    # 检查是否已有 SQLite 数据库
    if os.path.exists(db_path) and not dry_run:
        print(f"\n[WARNING] SQLite database already exists: {db_path}")
        response = input("Overwrite? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled")
            return
        os.remove(db_path)
    
    # 执行迁移
    if not dry_run:
        db = AuthorDatabaseSQLite(db_path)
        db.migrate_from_json(json_path)
        
        # 验证
        stats = db.get_statistics()
        print(f"\n[OK] Migration complete!")
        print(f"  SQLite authors: {stats['total_authors']}")
        print(f"  Senior researchers: {stats['senior_researchers']}")
        
        # 备份 JSON
        backup_path = json_path + '.backup'
        os.rename(json_path, backup_path)
        print(f"\n[OK] JSON backed up to: {backup_path}")
        
        print("\n" + "=" * 80)
        print("Next steps:")
        print("=" * 80)
        print("1. Set environment variable:")
        print("   Windows: set USE_SQLITE=true")
        print("   Linux/Mac: export USE_SQLITE=true")
        print("\n2. Or modify your scripts to use:")
        print("   from database_adapter import get_database")
        print("   db = get_database()")
        print("=" * 80)
    else:
        print("\n[DRY RUN] Would migrate:")
        print(f"  - {authors_count} authors to SQLite")
        print(f"  - Create database: {db_path}")
        print(f"  - Backup JSON to: {json_path}.backup")

if __name__ == '__main__':
    migrate()
