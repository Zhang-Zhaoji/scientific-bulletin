-- 国家/政权表
CREATE TABLE IF NOT EXISTS countries (
    id INTEGER PRIMARY KEY,
    en_name TEXT UNIQUE NOT NULL,
    ch_name TEXT,
    iso_code TEXT,
    conutry_name TEXT
);

-- 作者表
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    orcid TEXT UNIQUE,
    h_index INTEGER,
    citations INTEGER,
    normalized_name TEXT,
    UNIQUE(name, orcid)
);

-- 机构表
CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT,
    raw_affiliation TEXT,
    country_id INTEGER REFERENCES countries(id),
    article_id INTEGER REFERENCES articles(id),
    author_id INTEGER REFERENCES authors(id),
    UNIQUE(normalized_name)
);

-- 文章主表
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    doi TEXT UNIQUE,
    pmid TEXT,
    pmcid TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    journal TEXT,
    pub_date TEXT,
    pub_year INTEGER,
    source TEXT,
    is_open_access BOOLEAN,
    url TEXT,
    raw_json TEXT
);

-- 文章-作者关联
CREATE TABLE IF NOT EXISTS article_authors (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    author_id INTEGER REFERENCES authors(id),
    author_order INTEGER,
    is_senior_author BOOLEAN,
    PRIMARY KEY (article_id, author_id, author_order)
);

-- 文章-机构关联
CREATE TABLE IF NOT EXISTS article_institutions (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    institution_id INTEGER REFERENCES institutions(id),
    author_id INTEGER REFERENCES authors(id),
    PRIMARY KEY (article_id, institution_id)
);

-- 主题表
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- 文章-主题关联
CREATE TABLE IF NOT EXISTS article_themes (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    theme_id INTEGER REFERENCES themes(id),
    confidence REAL,
    PRIMARY KEY (article_id, theme_id)
);

CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,              -- 提取的片段（如 "Harvard Univ, USA"）
    normalized_name TEXT,            -- 标准化后的名称
    country_id INTEGER REFERENCES countries(id),
    raw_affiliation TEXT,            -- 原始完整字符串（新增）
    article_id INTEGER REFERENCES articles(id),
    author_id INTEGER REFERENCES authors(id),
    UNIQUE(name, country_id)         -- 同国家同片段视为同一机构
);