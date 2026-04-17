-- 国家/政权表
CREATE TABLE IF NOT EXISTS countries (
    id INTEGER PRIMARY KEY,
    en_name TEXT UNIQUE NOT NULL,
    ch_name TEXT,
    iso_code TEXT,
    conutry_name TEXT,
    standard_name TEXT
);

-- 作者表
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    orcid TEXT UNIQUE,
    h_index INTEGER,
    citations INTEGER,
    is_senior_researcher BOOLEAN,
    -- normalized_name TEXT, it seems not useful
    -- UNIQUE(name, orcid)
);

-- 机构表
CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    raw_affiliation TEXT,
    country_id INTEGER REFERENCES countries(id),
    -- country_id INTEGER REFERENCES countries(id),
    -- article_id INTEGER REFERENCES articles(id),
    -- author_id INTEGER REFERENCES authors(id),
    UNIQUE(normalized_name)
);

-- 文章主表
CREATE TABLE IF NOT EXISTS articles (
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
    -- raw_json TEXT
);

-- 主题表
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- 作者-机构关联
CREATE TABLE IF NOT EXISTS author_institutions (
    author_id INTEGER REFERENCES authors(id),
    institution_id INTEGER REFERENCES institutions(id),
    PRIMARY KEY (author_id, institution_id)
);

-- 文章-作者关联
CREATE TABLE IF NOT EXISTS article_authors (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    author_id INTEGER REFERENCES authors(id),
    PRIMARY KEY (article_id, author_id)
);

-- 文章-机构关联
CREATE TABLE IF NOT EXISTS article_institutions (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    institution_id INTEGER REFERENCES institutions(id),
    PRIMARY KEY (article_id, institution_id)
);

-- 文章-主题关联
CREATE TABLE IF NOT EXISTS article_themes (
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    theme_id INTEGER REFERENCES themes(id),
    PRIMARY KEY (article_id, theme_id)
);