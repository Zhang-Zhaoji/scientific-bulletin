"""
Author Enrichment Module

Enriches paper data with author information:
1. Author affiliations (from PubMed / Europe PMC)
2. Author impact metrics (from OpenAlex API)
3. Persistent caching of author/institution data

Features:
- Retry mechanism with exponential backoff
- Persistent database for authors and institutions
- Normalized affiliation list output
"""

import requests
import time
import json
import os
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from difflib import SequenceMatcher


@dataclass
class AuthorInfo:
    """作者信息数据结构"""
    name: str
    affiliation: Optional[str] = None
    normalized_affiliation: Optional[str] = None
    country: Optional[str] = None
    orcid: Optional[str] = None
    h_index: Optional[int] = None
    citations: Optional[int] = None
    works_count: Optional[int] = None
    i10_index: Optional[int] = None
    is_senior_researcher: bool = False
    last_updated: str = ""


# 大牛判定阈值（可配置）
SENIOR_RESEARCHER_THRESHOLD = {
    "h_index": 25,
    "total_citations": 3000,
    "works_count": 40,
    "i10_index": 40
}

# 数据库文件路径
DATA_DIR = "data"
AUTHOR_DB_FILE = os.path.join(DATA_DIR, "author_database.json")
INSTITUTION_DB_FILE = os.path.join(DATA_DIR, "institution_database.json")
SENIOR_RESEARCHERS_FILE = os.path.join(DATA_DIR, "senior_researchers.json")


class AuthorDatabase:
    """作者数据库管理类"""
    
    def __init__(self):
        self.authors: Dict[str, Dict] = {}
        self.institutions: Dict[str, Dict] = {}
        self.senior_researchers: Dict[str, Dict] = {}
        self._load_databases()
    
    def _load_databases(self):
        """加载所有数据库"""
        os.makedirs(DATA_DIR, exist_ok=True)
        
        if os.path.exists(AUTHOR_DB_FILE):
            with open(AUTHOR_DB_FILE, 'r', encoding='utf-8') as f:
                self.authors = json.load(f)
            print(f"[DB] Loaded {len(self.authors)} authors from database")
        
        if os.path.exists(INSTITUTION_DB_FILE):
            with open(INSTITUTION_DB_FILE, 'r', encoding='utf-8') as f:
                self.institutions = json.load(f)
            print(f"[DB] Loaded {len(self.institutions)} institutions from database")
        
        if os.path.exists(SENIOR_RESEARCHERS_FILE):
            with open(SENIOR_RESEARCHERS_FILE, 'r', encoding='utf-8') as f:
                self.senior_researchers = json.load(f)
            print(f"[DB] Loaded {len(self.senior_researchers)} senior researchers from database")
    
    def save_databases(self):
        """保存所有数据库"""
        with open(AUTHOR_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.authors, f, ensure_ascii=False, indent=2)
        
        with open(INSTITUTION_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.institutions, f, ensure_ascii=False, indent=2)
        
        with open(SENIOR_RESEARCHERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.senior_researchers, f, ensure_ascii=False, indent=2)
        
        print(f"[DB] Saved databases: {len(self.authors)} authors, {len(self.institutions)} institutions, {len(self.senior_researchers)} senior researchers")
    
    def get_author(self, name: str) -> Optional[Dict]:
        """从缓存获取作者信息"""
        return self.authors.get(name)
    
    def update_author(self, name: str, info: Dict, paper_date: str = ""):
        """更新作者信息，使用文章日期作为first_seen/last_seen"""
        info['last_updated'] = datetime.now().isoformat()
        
        # 使用文章日期而不是当前时间
        if paper_date:
            # 尝试解析日期格式
            try:
                # 支持格式: "14 Mar 2026" 或 "2026-03-14"
                for fmt in ['%d %b %Y', '%Y-%m-%d', '%d %B %Y']:
                    try:
                        parsed_date = datetime.strptime(paper_date, fmt)
                        date_str = parsed_date.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
                else:
                    date_str = paper_date
            except:
                date_str = paper_date
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        # 更新first_seen和last_seen
        if name not in self.authors:
            info['first_seen'] = date_str
            info['last_seen'] = date_str
        else:
            # 保留最早的first_seen，更新last_seen
            existing = self.authors[name]
            info['first_seen'] = existing.get('first_seen', date_str)
            # 比较日期，保留最晚的
            existing_last = existing.get('last_seen', date_str)
            info['last_seen'] = max(date_str, existing_last)
        
        self.authors[name] = info
        
        # 如果是大牛，更新大牛数据库
        if info.get('is_senior_researcher'):
            if name not in self.senior_researchers:
                self.senior_researchers[name] = {
                    'name': name,
                    'h_index': info.get('h_index'),
                    'citations': info.get('citations'),
                    'works_count': info.get('works_count'),
                    'affiliation': info.get('normalized_affiliation') or info.get('affiliation'),
                    'first_seen': info.get('first_seen', date_str),
                    'paper_count': 0
                }
            
            # 更新last_seen和paper_count
            sr = self.senior_researchers[name]
            sr['last_seen'] = max(sr.get('last_seen', date_str), date_str)
            sr['paper_count'] = sr.get('paper_count', 0) + 1
    
    def get_institution(self, name: str) -> Optional[Dict]:
        """从缓存获取单位信息"""
        return self.institutions.get(name)
    
    def update_institution(self, name: str, info: Dict, paper_date: str = ""):
        """更新单位信息，使用文章日期"""
        # 使用文章日期
        if paper_date:
            date_str = paper_date
            try:
                for fmt in ['%d %b %Y', '%Y-%m-%d', '%d %B %Y']:
                    try:
                        parsed_date = datetime.strptime(paper_date, fmt)
                        date_str = parsed_date.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
            except:
                pass
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        if name not in self.institutions:
            self.institutions[name] = {
                'name': name,
                'first_seen': date_str,
                'countries': [],
                'count': 0
            }
        
        # 更新last_seen和count
        existing_last = self.institutions[name].get('last_seen', date_str)
        self.institutions[name]['last_seen'] = max(date_str, existing_last)
        self.institutions[name]['count'] = self.institutions[name].get('count', 0) + 1
        
        # 更新国籍信息
        if info.get('country') and info['country'] not in self.institutions[name]['countries']:
            self.institutions[name]['countries'].append(info['country'])


# 全局数据库实例
_db = None

def get_database() -> AuthorDatabase:
    """获取数据库单例"""
    global _db
    if _db is None:
        _db = AuthorDatabase()
    return _db


def get_priority_authors(authors: List[str]) -> List[Tuple[int, str]]:
    """获取优先查询的作者：前3个 + 后3个（去重）"""
    if not authors:
        return []
    
    n = len(authors)
    indices = set()
    
    for i in range(min(3, n)):
        indices.add(i)
    
    for i in range(max(0, n-3), n):
        indices.add(i)
    
    return [(i, authors[i]) for i in sorted(indices)]


def fetch_with_retry(url: str, params: Dict, headers: Dict, max_retries: int = 3, delay: float = 1.0) -> Optional[Dict]:
    """带重试机制的 HTTP GET 请求"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            wait_time = delay * (2 ** attempt)
            print(f"      [RETRY {attempt+1}/{max_retries}] Timeout, waiting {wait_time}s...")
            time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            print(f"      [RETRY {attempt+1}/{max_retries}] Request error: {e}")
            time.sleep(delay * (2 ** attempt))
    
    print(f"      [FAIL] Max retries exceeded")
    return None


def split_affiliation(affiliation: str) -> List[str]:
    """
    分割单位字符串，按分号和句号分割
    
    例如：
    "Dept of A, Univ of B; Institute of C, Univ of D." 
    -> ["Dept of A, Univ of B", "Institute of C, Univ of D"]
    """
    if not affiliation:
        return []
    
    # 按分号或句号分割，但保留逗号分隔的部分
    parts = re.split(r'[;.]+', affiliation)
    
    # 清理并去重
    result = []
    for part in parts:
        cleaned = part.strip()
        # 过滤掉太短的片段（可能是噪声）
        if len(cleaned) > 5 and cleaned not in result:
            result.append(cleaned)
    
    return result


def infer_country_from_affiliation(affiliation: str) -> Optional[str]:
    """从单位名称推断国籍"""
    if not affiliation:
        return None
    
    affiliation_lower = affiliation.lower()
    
    country_keywords = {
        'usa': 'United States',
        'united states': 'United States',
        'harvard': 'United States',
        'stanford': 'United States',
        'mit ': 'United States',
        'university of california': 'United States',
        'uc ': 'United States',
        'yale': 'United States',
        'princeton': 'United States',
        'columbia university': 'United States',
        'johns hopkins': 'United States',
        'china': 'China',
        'chinese academy': 'China',
        'peking university': 'China',
        'tsinghua': 'China',
        'fudan': 'China',
        'zhejiang': 'China',
        'shanghai jiao tong': 'China',
        'nanjing university': 'China',
        'uk': 'United Kingdom',
        'united kingdom': 'United Kingdom',
        'cambridge': 'United Kingdom',
        'oxford': 'United Kingdom',
        'imperial college': 'United Kingdom',
        'ucl': 'United Kingdom',
        'university college london': 'United Kingdom',
        'germany': 'Germany',
        'german': 'Germany',
        'max planck': 'Germany',
        'france': 'France',
        'paris': 'France',
        'sorbonne': 'France',
        'japan': 'Japan',
        'tokyo': 'Japan',
        'canada': 'Canada',
        'toronto': 'Canada',
        'mcgill': 'Canada',
        'australia': 'Australia',
        'switzerland': 'Switzerland',
        'eth z': 'Switzerland',
        'swiss': 'Switzerland',
        'netherlands': 'Netherlands',
        'sweden': 'Sweden',
        'karolinska': 'Sweden',
        'denmark': 'Denmark',
        'italy': 'Italy',
        'spain': 'Spain',
        'israel': 'Israel',
        'weizmann': 'Israel',
    }
    
    for keyword, country in country_keywords.items():
        if keyword in affiliation_lower:
            return country
    
    return None


def normalize_affiliation(affiliation: str) -> str:
    """标准化单位名称"""
    if not affiliation:
        return ""
    
    normalized = " ".join(affiliation.split())
    normalized = normalized.title()
    
    return normalized


def fetch_affiliations_from_pubmed(pmid: str, delay: float = 0.3) -> Dict[str, str]:
    """从 PubMed API 获取作者单位信息"""
    if not pmid:
        return {}
    
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        'db': 'pubmed',
        'id': pmid,
        'retmode': 'xml',
        'rettype': 'abstract'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        from xml.etree import ElementTree as ET
        root = ET.fromstring(response.content)
        
        affiliations = {}
        
        for author in root.findall('.//Author'):
            last_name = author.find('LastName')
            fore_name = author.find('ForeName')
            
            if last_name is not None:
                name = last_name.text or ""
                if fore_name is not None and fore_name.text:
                    name = f"{fore_name.text} {name}"
                
                affil = author.find('AffiliationInfo/Affiliation')
                if affil is not None and affil.text:
                    affiliations[name] = affil.text
        
        time.sleep(delay)
        return affiliations
        
    except Exception as e:
        print(f"    [WARN] PubMed fetch error for PMID {pmid}: {e}")
        return {}


# ============== Strict Matching Functions ==============

# 常见中文姓氏
CHINESE_SURNAMES = {
    'Li', 'Wang', 'Zhang', 'Liu', 'Chen', 'Yang', 'Zhao', 'Huang', 'Zhou',
    'Wu', 'Xu', 'Sun', 'Ma', 'Zhu', 'Hu', 'Guo', 'He', 'Gao', 'Lin',
    'Dong', 'Zong', 'Tang', 'Kong', 'Zheng', 'Xie', 'Han', 'Feng', 'Yu',
    'Xiao', 'Ye', 'Cheng', 'Cao', 'Yuan', 'Deng', 'Fu', 'Shen',
    'Zeng', 'Peng', 'Lu', 'Su', 'Jiang', 'Cai', 'Jia', 'Ding', 'Wei',
    'Xue', 'Tian', 'Pan', 'Du', 'Dai', 'Zhong', 'Fan', 'Fang', 'Shi',
    'Yao', 'Tan', 'Mao', 'Xiong', 'Gu', 'Hao', 'Bai', 'Shao', 'Qian',
    'Long', 'Wan', 'Duan', 'Lei', 'Qin', 'An', 'Yi', 'Yan', 'Niu',
    'Yin', 'Chang', 'Luo', 'Qi', 'Wen', 'Qu', 'Qiao', 'Zou', 'Jin',
    'Qiu', 'Hong', 'You', 'Bao', 'Chu', 'Lai', 'Gan', 'Nie', 'Chao',
}

# 可疑阈值
SUSPICIOUS_CITATIONS = 200000  # 引用数超过20万标记为可疑


def classify_name(name: str) -> str:
    """
    判断名字类型
    返回: "strict" (严格模式) 或 "loose" (宽松模式)
    """
    parts = name.strip().split()
    if not parts:
        return "loose"
    
    # 检测缩写: "Tang S", "Zong L."
    is_abbreviation = False
    if len(parts) >= 2:
        last = parts[-1].rstrip('.')
        if len(last) <= 2 and last.isalpha():
            is_abbreviation = True
    
    # 检测中文姓氏
    is_chinese = parts[0] in CHINESE_SURNAMES
    
    if is_abbreviation or is_chinese:
        return "strict"
    
    return "loose"


def name_similarity(name1: str, name2: str) -> float:
    """计算名字相似度"""
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()


def check_affiliation_match(pubmed_affil: str, openalex_affil: str) -> bool:
    """检查两个单位是否匹配"""
    if not pubmed_affil or not openalex_affil:
        return False
    
    a1 = pubmed_affil.lower()
    a2 = openalex_affil.lower()
    
    # 直接包含
    if a1 in a2 or a2 in a1:
        return True
    
    # 提取关键词
    def extract_keywords(text):
        words = re.findall(r'\b[a-z]{4,}\b', text)
        return set(words)
    
    k1 = extract_keywords(a1)
    k2 = extract_keywords(a2)
    
    # 有共同关键词
    if k1 & k2:
        return True
    
    # 模糊匹配
    return SequenceMatcher(None, a1, a2).ratio() > 0.6


def fetch_author_impact_strict(author_name: str, 
                                pubmed_affiliation: str,
                                delay: float = 0.3) -> Optional[Dict]:
    """
    严格模式获取作者信息
    要求: 名字相似 + 单位匹配
    宁缺毋滥: 不匹配返回 None
    """
    # 必须有 PubMed 单位信息
    if not pubmed_affiliation:
        print(f"        [SKIP STRICT] No affiliation for {author_name}")
        return None
    
    url = "https://api.openalex.org/authors"
    params = {'search': author_name, 'per-page': 10}
    headers = {'User-Agent': 'mailto:zhang-zj@stu.pku.edu.cn'}
    
    data = fetch_with_retry(url, params, headers, max_retries=3, delay=delay)
    if not data or not data.get('results'):
        return None
    
    candidates = data['results']
    
    # 名字严格匹配 (>0.9)
    name_matches = []
    for c in candidates:
        sim = name_similarity(author_name, c.get('display_name', ''))
        if sim > 0.9:
            name_matches.append((c, sim))
    
    if not name_matches:
        print(f"        [SKIP STRICT] No name match >0.9 for {author_name}")
        return None
    
    # 按相似度排序
    name_matches.sort(key=lambda x: -x[1])
    
    # 单位匹配检查
    for candidate, sim in name_matches:
        # 获取候选人的单位
        cand_affiliations = []
        
        last_inst = candidate.get('last_known_institution')
        if last_inst:
            cand_affiliations.append(last_inst.get('display_name', ''))
        
        # 检查单位匹配
        for cand_affil in cand_affiliations:
            if check_affiliation_match(pubmed_affiliation, cand_affil):
                citations = candidate.get('cited_by_count', 0)
                
                result = {
                    'name': candidate.get('display_name', author_name),
                    'h_index': candidate.get('summary_stats', {}).get('h_index', 0),
                    'citations': citations,
                    'works_count': candidate.get('works_count', 0),
                    'i10_index': candidate.get('summary_stats', {}).get('i10_index', 0),
                    'orcid': candidate.get('orcid'),
                    'affiliation': cand_affil,
                    'match_confidence': 'high',
                }
                
                # 标记可疑的高引用
                if citations > SUSPICIOUS_CITATIONS:
                    result['suspicious'] = True
                    result['warning'] = f"Citations {citations} > {SUSPICIOUS_CITATIONS}, please verify"
                    print(f"        [WARNING] Suspicious high citations: {citations}")
                
                return result
    
    # 没有单位匹配
    print(f"        [SKIP STRICT] No affiliation match for {author_name}")
    return None


def fetch_author_impact_loose(author_name: str, delay: float = 0.3) -> Optional[Dict]:
    """宽松模式获取作者信息"""
    url = "https://api.openalex.org/authors"
    params = {'search': author_name, 'per-page': 5}
    headers = {'User-Agent': 'mailto:zhang-zj@stu.pku.edu.cn'}
    
    data = fetch_with_retry(url, params, headers, max_retries=3, delay=delay)
    if not data or not data.get('results'):
        return None
    
    # 取最相似的
    best = max(data['results'], 
               key=lambda x: name_similarity(author_name, x.get('display_name', '')))
    
    sim = name_similarity(author_name, best.get('display_name', ''))
    if sim < 0.8:
        print(f"        [SKIP LOOSE] Best match similarity {sim:.2f} < 0.8")
        return None
    
    citations = best.get('cited_by_count', 0)
    last_inst = best.get('last_known_institution', {})
    
    result = {
        'name': best.get('display_name', author_name),
        'h_index': best.get('summary_stats', {}).get('h_index', 0),
        'citations': citations,
        'works_count': best.get('works_count', 0),
        'i10_index': best.get('summary_stats', {}).get('i10_index', 0),
        'orcid': best.get('orcid'),
        'affiliation': last_inst.get('display_name', ''),
        'match_confidence': 'medium',
    }
    
    if citations > SUSPICIOUS_CITATIONS:
        result['suspicious'] = True
        result['warning'] = f"Citations {citations} > {SUSPICIOUS_CITATIONS}, please verify"
        print(f"        [WARNING] Suspicious high citations: {citations}")
    
    return result


def fetch_author_impact_from_openalex(author_name: str, 
                                       pubmed_affiliation: Optional[str] = None,
                                       delay: float = 0.3) -> Optional[Dict]:
    """
    智能选择匹配策略
    """
    mode = classify_name(author_name)
    
    if mode == "strict":
        return fetch_author_impact_strict(author_name, pubmed_affiliation, delay)
    else:
        return fetch_author_impact_loose(author_name, delay)


def is_senior_researcher(metrics: Dict, thresholds: Dict = SENIOR_RESEARCHER_THRESHOLD) -> bool:
    """判断是否为资深研究者/大牛"""
    if not metrics:
        return False
    
    return (
        metrics.get('h_index', 0) >= thresholds['h_index'] or
        metrics.get('citations', 0) >= thresholds['total_citations'] or
        metrics.get('works_count', 0) >= thresholds['works_count'] or
        metrics.get('i10_index', 0) >= thresholds['i10_index']
    )


def enrich_paper_authors(paper: Dict, 
                         enable_affiliation: bool = True,
                         enable_impact: bool = True,
                         delay: float = 0.3) -> Dict:
    """
    增强论文的作者信息
    
    Returns:
        包含增强作者信息的论文字典，新增字段：
        - affiliations: List[str]  # 分割去重后的单位列表
        - author_details: List[Dict]  # 详细作者信息
        - senior_authors: List[Dict]  # 大牛作者详细信息（含引用数、机构、文章数）
        - senior_author_count: int
        - has_senior_researcher: bool
        - countries: List[str]  # 国家列表
    """
    db = get_database()
    authors = paper.get('authors', [])
    paper_date = paper.get('date', '')
    
    if not authors:
        return paper
    
    enriched = paper.copy()
    priority_authors = get_priority_authors(authors)
    
    print(f"  Enriching {len(priority_authors)}/{len(authors)} priority authors...")
    
    # 1. 获取单位信息
    affiliations_map = {}
    if enable_affiliation:
        pmid = paper.get('pmid', '')
        if pmid:
            print(f"    Fetching affiliations from PubMed (PMID: {pmid})...")
            affiliations_map = fetch_affiliations_from_pubmed(pmid, delay=delay)
            print(f"    Found {len(affiliations_map)} affiliations")
    
    # 2. 处理每个作者
    author_details = []
    senior_authors_info = []  # 存储大牛的详细信息
    all_affiliations = []  # 所有分割后的单位
    all_countries = []
    
    if enable_impact:
        for idx, author_name in priority_authors:
            cached = db.get_author(author_name)
            
            if cached:
                print(f"    [{idx+1}] {author_name} [CACHED]")
                info = cached
            else:
                print(f"    [{idx+1}] {author_name} [FETCHING]...")
                
                info = {
                    'name': author_name,
                    'affiliation': None,
                    'normalized_affiliation': None,
                    'country': None,
                    'orcid': None,
                    'h_index': None,
                    'citations': None,
                    'works_count': None,
                    'i10_index': None,
                    'is_senior_researcher': False
                }
                
                # 获取单位
                if author_name in affiliations_map:
                    affil = affiliations_map[author_name]
                    info['affiliation'] = affil
                    info['normalized_affiliation'] = normalize_affiliation(affil)
                    info['country'] = infer_country_from_affiliation(affil)
                
                # 获取影响力指标（传递单位信息进行严格匹配）
                author_affil = affiliations_map.get(author_name, '')
                metrics = fetch_author_impact_from_openalex(author_name, author_affil, delay=delay)
                if metrics:
                    info['h_index'] = metrics.get('h_index')
                    info['citations'] = metrics.get('citations')
                    info['works_count'] = metrics.get('works_count')
                    info['i10_index'] = metrics.get('i10_index')
                    info['orcid'] = metrics.get('orcid')
                    info['is_senior_researcher'] = is_senior_researcher(metrics)
                    info['source'] = 'OpenAlex'
                    
                    status = "SENIOR" if info['is_senior_researcher'] else "OK"
                    print(f"        [{status}] h={info['h_index']}, cites={info['citations']}")
                else:
                    print(f"        [NOT FOUND]")
                    info['source'] = 'Not found'
                
                # 更新数据库（使用文章日期）
                db.update_author(author_name, info, paper_date)
            
            # 收集结果
            author_details.append(info)
            
            # 分割单位并收集
            if info.get('affiliation'):
                split_affils = split_affiliation(info['affiliation'])
                for affil in split_affils:
                    norm_affil = normalize_affiliation(affil)
                    if norm_affil and norm_affil not in all_affiliations:
                        all_affiliations.append(norm_affil)
                    # 更新单位数据库
                    country = infer_country_from_affiliation(affil)
                    db.update_institution(norm_affil, {'country': country}, paper_date)
            
            if info.get('country') and info['country'] not in all_countries:
                all_countries.append(info['country'])
            
            # 如果是大牛，收集详细信息
            if info.get('is_senior_researcher'):
                senior_info = {
                    'name': author_name,
                    'h_index': info.get('h_index'),
                    'citations': info.get('citations'),
                    'works_count': info.get('works_count'),
                    'institution': info.get('normalized_affiliation') or info.get('affiliation', 'N/A'),
                }
                senior_authors_info.append(senior_info)
    
    # 3. 构建返回结果
    enriched['affiliations'] = all_affiliations
    enriched['author_details'] = author_details
    enriched['senior_authors'] = senior_authors_info  # 现在包含详细信息
    enriched['senior_author_names'] = [s['name'] for s in senior_authors_info]  # 保留名字列表方便使用
    enriched['senior_author_count'] = len(senior_authors_info)
    enriched['has_senior_researcher'] = len(senior_authors_info) > 0
    enriched['countries'] = all_countries
    enriched['author_enrichment_status'] = 'enriched' if author_details else 'failed'
    
    # 保存数据库
    db.save_databases()
    
    return enriched


# ============== Test Functions ==============

def test_author_enrichment():
    """测试作者增强功能"""
    import jsonlines
    
    print("=" * 80)
    print("Testing Author Enrichment with Improved Features")
    print("=" * 80)
    
    # Load test papers
    with jsonlines.open('getfiles/all_papers_2026-03-14-noscience.jsonl') as f:
        papers = list(f)
    
    # Test first 3 papers
    for i, paper in enumerate(papers[:3], 1):
        print(f"\n[{i}] {paper['title'][:60]}...")
        print(f"    Date: {paper.get('date', 'N/A')}")
        print(f"    Authors: {paper.get('authors', [])}")
        
        enriched = enrich_paper_authors(paper, enable_affiliation=True, enable_impact=True)
        
        print(f"\n    === Result ===")
        print(f"    Status: {enriched.get('author_enrichment_status')}")
        print(f"    Senior authors ({enriched.get('senior_author_count')}):")
        
        # 显示大牛详细信息
        for sr in enriched.get('senior_authors', []):
            print(f"      - {sr['name']}")
            print(f"        h-index: {sr['h_index']}, citations: {sr['citations']}, works: {sr['works_count']}")
            affil = sr.get('institution', 'N/A') or 'N/A'
            print(f"        institution: {affil[:50]}...")
        
        print(f"\n    Affiliations ({len(enriched.get('affiliations', []))}):")
        for affil in enriched.get('affiliations', [])[:5]:
            print(f"      - {affil[:60]}...")
        
        print(f"\n    Countries: {enriched.get('countries', [])}")
        print("-" * 80)


if __name__ == '__main__':
    test_author_enrichment()
