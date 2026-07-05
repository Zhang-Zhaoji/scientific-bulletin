"""
构建精简版 SQLite 数据库，用于静态网站 Dashboard 可视化。

从 data/literature.db 复制，清空大文本字段（abstract, title_zh, url, doi, raw_affiliation），
VACUUM 回收空间后输出到 docs/assets/data/literature_slim.db。

精简数据库保留了所有可视化所需的字段：
- articles: id, title, pmid, pmcid, journal, pub_date, pub_year, is_open_access, score
- authors: id, name, orcid, h_index, citations, is_senior_researcher
- institutions: id, name, country_id, normalized_name
- countries, themes, subthemes, crosstags 及所有关联表保持不变
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path


# 需要清空的大字段
SLIM_FIELDS = {
    "articles": ["abstract", "title_zh", "url", "doi"],
    "institutions": ["raw_affiliation"],
}

# 默认路径
DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "data" / "literature.db"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "data" / "literature_slim.db"


def build_slim_db(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> Path:
    """构建精简数据库。

    Args:
        input_path: 完整数据库路径
        output_path: 精简数据库输出路径

    Returns:
        精简数据库路径
    """
    if not input_path.exists():
        raise FileNotFoundError(f"源数据库不存在: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 复制数据库
    print(f"复制数据库: {input_path}")
    print(f"  原始大小: {input_path.stat().st_size / 1024 / 1024:.2f} MB")
    shutil.copy2(input_path, output_path)

    # 清空大字段
    conn = sqlite3.connect(str(output_path))
    cur = conn.cursor()

    for table, fields in SLIM_FIELDS.items():
        for field in fields:
            # 检查字段是否存在
            cols = cur.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = [col[1] for col in cols]
            if field not in col_names:
                print(f"  跳过 {table}.{field}（字段不存在）")
                continue

            # 统计清空前的大小
            result = cur.execute(
                f'SELECT COALESCE(SUM(LENGTH("{field}")), 0) FROM {table}'
            ).fetchone()
            saved_bytes = result[0] or 0

            cur.execute(f'UPDATE {table} SET "{field}" = NULL')
            print(f"  清空 {table}.{field}（节省 {saved_bytes / 1024:.0f} KB）")

    conn.commit()

    # 转换 pub_date 格式为 ISO (YYYY-MM-DD)
    # 源数据可能是 "DD MMM YYYY"（如 "15 Mar 2026"），此格式无法用 BETWEEN 正确排序
    print("转换 pub_date 为 ISO 格式...")
    from datetime import datetime
    rows = cur.execute("SELECT id, pub_date FROM articles WHERE pub_date IS NOT NULL").fetchall()
    converted = 0
    for article_id, date_str in rows:
        try:
            dt = datetime.strptime(date_str, '%d %b %Y')
            cur.execute("UPDATE articles SET pub_date = ? WHERE id = ?", (dt.strftime('%Y-%m-%d'), article_id))
            converted += 1
        except ValueError:
            pass  # 跳过无法解析或已是 ISO 格式的日期
    conn.commit()
    if converted:
        print(f"  已转换 {converted} 条日期")
    else:
        print("  所有日期已是 ISO 格式，无需转换")

    # VACUUM 回收空间
    print("VACUUM 回收空间...")
    conn.execute("VACUUM")
    conn.close()

    slim_size = output_path.stat().st_size
    orig_size = input_path.stat().st_size
    print(f"精简数据库: {slim_size / 1024 / 1024:.2f} MB（节省 {(orig_size - slim_size) / 1024 / 1024:.2f} MB, {(orig_size - slim_size) / orig_size * 100:.0f}%)")

    return output_path


def verify_slim_db(input_path: Path, output_path: Path) -> bool:
    """验证精简数据库的完整性。

    检查：
    1. 所有表存在且行数一致
    2. 大字段已清空
    3. 保留字段数据完整
    4. 关联表完整性
    """
    print("\n验证精简数据库...")
    orig = sqlite3.connect(str(input_path))
    slim = sqlite3.connect(str(output_path))

    success = True

    # 1. 检查所有表行数一致
    tables = orig.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    for (table,) in tables:
        orig_count = orig.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        slim_count = slim.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if orig_count != slim_count:
            print(f"  ✗ {table}: 行数不一致（{orig_count} vs {slim_count}）")
            success = False
        else:
            print(f"  ✓ {table}: {slim_count} 行")

    # 2. 检查大字段已清空
    for table, fields in SLIM_FIELDS.items():
        for field in fields:
            cols = slim.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = [col[1] for col in cols]
            if field not in col_names:
                continue
            non_null = slim.execute(
                f'SELECT COUNT(*) FROM {table} WHERE "{field}" IS NOT NULL'
            ).fetchone()[0]
            if non_null > 0:
                print(f"  ✗ {table}.{field}: 仍有 {non_null} 条非空记录")
                success = False
            else:
                print(f"  ✓ {table}.{field}: 已全部清空")

    # 3. 检查保留字段数据完整（抽样对比 articles 表）
    orig_sample = orig.execute(
        "SELECT id, title, journal, pub_date, score FROM articles ORDER BY id LIMIT 5"
    ).fetchall()
    slim_sample = slim.execute(
        "SELECT id, title, journal, pub_date, score FROM articles ORDER BY id LIMIT 5"
    ).fetchall()

    if orig_sample == slim_sample:
        print("  ✓ 保留字段数据完整（抽样对比一致）")
    else:
        print("  ✗ 保留字段数据不一致")
        success = False

    # 4. 检查关键SQL查询能否正常执行
    test_queries = [
        ("国家发文量", """
            SELECT c.standard_name, COUNT(*) as cnt
            FROM articles a
            JOIN article_countries ac ON a.id = ac.article_id
            JOIN countries c ON ac.country_id = c.id
            GROUP BY c.standard_name ORDER BY cnt DESC LIMIT 5
        """),
        ("领域分布", """
            SELECT t.name, COUNT(*) as cnt
            FROM articles a
            JOIN article_themes at ON a.id = at.article_id
            JOIN themes t ON at.theme_id = t.id
            GROUP BY t.name ORDER BY cnt DESC
        """),
        ("国家×领域交叉", """
            SELECT c.standard_name, t.name, COUNT(*) as cnt
            FROM articles a
            JOIN article_countries ac ON a.id = ac.article_id
            JOIN countries c ON ac.country_id = c.id
            JOIN article_themes at ON a.id = at.article_id
            JOIN themes t ON at.theme_id = t.id
            GROUP BY c.standard_name, t.name
            ORDER BY cnt DESC LIMIT 5
        """),
        ("评分分布", """
            SELECT CAST(score AS INTEGER) as bin, COUNT(*) as cnt
            FROM articles WHERE score > 0
            GROUP BY bin ORDER BY bin
        """),
        ("期刊排名", """
            SELECT journal, COUNT(*) as cnt, AVG(score) as avg_score
            FROM articles WHERE journal IS NOT NULL
            GROUP BY journal ORDER BY cnt DESC LIMIT 5
        """),
        ("机构排名", """
            SELECT i.name, COUNT(*) as cnt, AVG(a.score) as avg_score
            FROM articles a
            JOIN article_institutions ai ON a.id = ai.article_id
            JOIN institutions i ON ai.institution_id = i.id
            GROUP BY i.name ORDER BY cnt DESC LIMIT 5
        """),
        ("交叉标签", """
            SELECT ct.name, COUNT(*) as cnt
            FROM article_crosstags act
            JOIN crosstags ct ON act.tag_id = ct.id
            GROUP BY ct.name ORDER BY cnt DESC LIMIT 10
        """),
    ]

    print("\n  关键SQL查询测试:")
    for name, query in test_queries:
        try:
            results = slim.execute(query).fetchall()
            print(f"    ✓ {name}: {len(results)} 条结果")
        except Exception as e:
            print(f"    ✗ {name}: {e}")
            success = False

    orig.close()
    slim.close()

    if success:
        print("\n  ✓ 精简数据库验证通过")
    else:
        print("\n  ✗ 精简数据库验证失败")

    return success


def main():
    import argparse

    parser = argparse.ArgumentParser(description="构建精简版 SQLite 数据库")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="源数据库路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出路径")
    parser.add_argument("--verify", action="store_true", default=True, help="构建后验证")
    parser.add_argument("--no-verify", dest="verify", action="store_false", help="跳过验证")

    args = parser.parse_args()

    output = build_slim_db(args.input, args.output)

    if args.verify:
        if not verify_slim_db(args.input, output):
            print("\n[ERROR] 验证失败，请检查精简数据库", file=sys.stderr)
            sys.exit(1)

    print(f"\n[OK] 精简数据库已生成: {output}")
    return output


if __name__ == "__main__":
    main()
