import sqlite3
import os

def init_db(db_path="data/literature.db"):
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    conn = sqlite3.connect(db_path)
    conn.executescript(open('sql_scripts/schema.sql', 'r', encoding='utf-8').read())
    return conn


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
    if not columns:
        raise ValueError("search_item: columns cannot be empty")
    if len(columns) != len(values):
        raise ValueError(f"search_item: columns length ({len(columns)}) != values length ({len(values)})")
    
    conditions = []
    for col, val in zip(columns, values):
        if val is None:
            conditions.append(f"{col} IS NULL")
        else:
            conditions.append(f"{col} = ?")
    
    where_cond = ' AND '.join(conditions)
    
    non_null_values = [val for val in values if val is not None]
    
    query = f"""
        SELECT id FROM {table_name} 
        WHERE {where_cond};
    """
    cursor = conn.execute(query, tuple(non_null_values))
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
    result = cursor.fetchone()
    return result[0]


def search_or_insert(conn, table_name: str, conflict_columns: list[str], insert_data: dict[str, any]) -> int:
    """
    Search for an item in the database by multiple columns, return the id of the existing item if found, or insert a new item if not found and return the inserted id.
    """
    validate_request(table_name, conflict_columns, insert_data)
    conflict_values = [insert_data[col] for col in conflict_columns]
    existing_ids = search_item(conn, table_name, conflict_columns, conflict_values)
    if existing_ids is not None:
        if table_name in ['countries', 'articles', 'institutions', 'themes', 'subthemes', 'crosstags', 'author_institutions', 'article_authors', 'article_institutions', 'article_themes', 'article_subthemes', 'article_crosstags']:
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