"""
Paper Enrichment Module

This module enriches paper metadata from various sources:
1. Europe PMC - Primary source for published articles (via DOI/PMID)
2. bioRxiv - Preprint server fallback
3. arXiv - Preprint server fallback

Usage:
    from enrich_papers import enrich_papers_from_science
    
    # Science papers with basic info (title, authors, url, date)
    science_papers = [...]
    
    # Enrich with abstracts and other metadata
    enriched_papers = enrich_papers_from_science(science_papers)
"""

import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

# Import our crawlers
from crawler_europepmc import search_by_doi, search_by_title, fetch_article_by_identifier
from crawler_biorxiv import fetch_recent_biorxiv_papers
from crawler_arxiv import fetch_arxiv_papers


def extract_doi_from_url(url: str) -> Optional[str]:
    """
    Extract DOI from various URL formats.
    
    Supports:
    - https://www.science.org/doi/10.1126/science.abc123
    - https://doi.org/10.1126/science.abc123
    - /doi/10.1126/science.abc123
    - 10.1126/science.abc123 (already a DOI)
    """
    if not url:
        return None
    
    url = url.strip()
    
    # Direct DOI pattern (10.xxxx/...)
    if url.startswith('10.'):
        return url
    
    # Extract from URL path
    # Patterns:
    # - /doi/10.xxxx/...
    # - /doi/abs/10.xxxx/...
    # - /doi/full/10.xxxx/...
    
    if '/doi/' in url:
        parts = url.split('/doi/')
        if len(parts) > 1:
            doi_part = parts[1]
            # Remove common suffixes
            for prefix in ['abs/', 'full/', 'pdf/', 'epub/']:
                if doi_part.startswith(prefix):
                    doi_part = doi_part[len(prefix):]
            # DOI starts with 10.
            if doi_part.startswith('10.'):
                return doi_part.split('?')[0].split('#')[0].rstrip('/')
    
    # Try to parse URL
    try:
        parsed = urlparse(url)
        path = parsed.path
        
        # Look for 10. pattern in path
        if '10.' in path:
            idx = path.find('10.')
            doi = path[idx:]
            # Clean up
            doi = doi.split('?')[0].split('#')[0].rstrip('/')
            if doi.startswith('10.'):
                return doi
    except Exception:
        pass
    
    return None


def extract_doi_from_title(title: str) -> Optional[str]:
    """
    Try to extract DOI from title (some titles might contain DOI).
    """
    import re
    # DOI pattern: 10.xxxx/...
    pattern = r'10\.\d{4,}/[^\s]+'
    match = re.search(pattern, title)
    if match:
        return match.group(0)
    return None


import requests
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from difflib import SequenceMatcher

def is_similar_title(title1: str, title2: str, threshold: float = 0.85) -> bool:
    """计算标题相似度，容忍标点符号的细微差异"""
    if not title1 or not title2:
        return False
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() >= threshold

def extract_last_names(authors: List[str]) -> set:
    """提取作者姓氏用于交叉验证"""
    last_names = set()
    for author in authors:
        parts = author.split()
        if parts:
            last_names.add(parts[-1].lower().strip(','))
    return last_names

def clean_abstract(raw_abstract: str) -> str:
    """清除摘要中的 XML/HTML 标签 (例如 <jats:p>)"""
    if not raw_abstract:
        return ""
    # 用正则表达式移除所有 <...> 标签
    clean_text = re.sub(r'<[^>]+>', '', raw_abstract)
    # 移除可能残留的 "Abstract" 标题字样并去除首尾空格
    if clean_text.lower().startswith("abstract"):
        clean_text = clean_text[8:].strip()
    return clean_text

def search_preprint_servers(title: str, authors: List[str], days: int = 730) -> Optional[Dict]:
    cutoff_date = datetime.now() - timedelta(days=days)
    target_last_names = extract_last_names(authors)
    
    crossref_url = "https://api.crossref.org/works"
    
    params = {
        "query.title": title,
        "filter": "type:posted-content", # 限制搜索范围为预印本
        "rows": 5
    }
    
    headers = {"User-Agent": "PreprintTracker/1.0 (mailto:zhang-zj@stu.pku.edu.cn)"}
    
    try:
        response = requests.get(crossref_url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            items = response.json().get("message", {}).get("items", [])
            for item in items:
                publisher = item.get("publisher", "").lower()
                
                # 兼容不同结构的机构名
                institutions = item.get("institution", [])
                institution_name = institutions[0].get("name", "").lower() if institutions else ""
                
                # 确认是 bioRxiv 或 medRxiv
                if "biorxiv" in publisher or "biorxiv" in institution_name or "medrxiv" in institution_name:
                    found_title = item.get("title", [""])[0]
                    
                    if is_similar_title(title, found_title):
                        date_info = item.get("posted", item.get("accepted", item.get("issued", {})))
                        date_parts = date_info.get("date-parts", [[1970, 1, 1]])[0]
                        
                        if len(date_parts) == 3:
                            post_date = datetime(date_parts[0], date_parts[1], date_parts[2])
                            
                            # 验证时间窗口
                            if post_date >= cutoff_date:
                                found_authors = [a.get("family", "") for a in item.get("author", [])]
                                found_last_names = set(a.lower() for a in found_authors)
                                
                                # 验证作者姓氏是否有交集
                                if target_last_names & found_last_names or not authors:
                                    server_name = "bioRxiv" if "biorxiv" in institution_name or "biorxiv" in publisher else "medRxiv"
                                    
                                    # 【新增提取与清洗摘要的代码】
                                    raw_abstract = item.get("abstract", "")
                                    abstract_text = clean_abstract(raw_abstract)
                                    
                                    return {
                                        "server": server_name,
                                        "title": found_title,
                                        "doi": item.get("DOI"),
                                        "url": item.get("URL", [None])[0] if isinstance(item.get("URL"), list) else item.get("URL"),
                                        "date": post_date.strftime("%Y-%m-%d"),
                                        "abstract": abstract_text # <--- 这里返回摘要
                                    }
        else:
            print(f"API Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"Error searching bioRxiv via Crossref: {e}")

    return None


def enrich_single_paper(paper: Dict, delay: float = 0.5) -> Dict:
    """
    Enrich a single paper with metadata from external sources.
    
    Args:
        paper: Paper dict with at least 'title', 'url', 'authors', 'date'
        delay: Delay between API calls
    
    Returns:
        Enriched paper dict
    """
    title = paper.get('title', '')
    url = paper.get('url', '')
    authors = paper.get('authors', [])
    
    print(f"  Enriching: {title[:70]}...")
    
    # Try to extract DOI from URL
    doi = extract_doi_from_url(url)
    
    if not doi:
        # Try to extract from title
        doi = extract_doi_from_title(title)
    
    enriched = paper.copy()
    enriched['enrichment_status'] = 'original'
    enriched['source'] = paper.get('source', 'Unknown')
    
    # Step 1: Try Europe PMC via DOI
    if doi:
        print(f"    Trying Europe PMC (DOI: {doi[:40]}...)")
        try:
            result = search_by_doi(doi)
            if result:
                # Merge Europe PMC data
                enriched.update({
                    'abstract': result.get('abstract', paper.get('abstract', '')),
                    'pmid': result.get('pmid', ''),
                    'pmcid': result.get('pmcid', ''),
                    'doi': doi,
                    'journal': result.get('journal', paper.get('journal', '')),
                    'is_open_access': result.get('is_open_access', False),
                    'enrichment_status': 'europepmc_doi',
                    'source': f'{enriched["source"]} + Europe PMC'
                })
                print(f"    [OK] Found in Europe PMC (PMID: {result.get('pmid', 'N/A')})")
                time.sleep(delay)
                return enriched
        except Exception as e:
            print(f"    Europe PMC error: {e}")
    
    # Step 2: Try Europe PMC via title
    print(f"    Trying Europe PMC (title search)...")
    try:
        result = search_by_title(title)
        if result:
            # Check if it's a good match
            similarity = calculate_title_similarity(title, result['title'])
            if similarity > 0.8:
                enriched.update({
                    'abstract': result.get('abstract', paper.get('abstract', '')),
                    'pmid': result.get('pmid', ''),
                    'pmcid': result.get('pmcid', ''),
                    'doi': result.get('doi', doi or ''),
                    'journal': result.get('journal', paper.get('journal', '')),
                    'is_open_access': result.get('is_open_access', False),
                    'enrichment_status': 'europepmc_title',
                    'source': f'{enriched["source"]} + Europe PMC'
                })
                print(f"    [OK] Found in Europe PMC by title (similarity: {similarity:.2f})")
                time.sleep(delay)
                return enriched
            else:
                print(f"    [SKIP] Title similarity too low ({similarity:.2f})")
    except Exception as e:
        print(f"    Europe PMC title search error: {e}")
    
    # Step 3: Try preprint servers (for very recent papers)
    print(f"    Trying preprint servers...")
    try:
        preprint = search_preprint_servers(title, authors, days=60)
        if preprint:
            enriched.update({
                'abstract': preprint.get('abstract', paper.get('abstract', '')),
                'doi': preprint.get('doi', doi or ''),
                'pdf_url': preprint.get('pdf_url', ''),
                'enrichment_status': 'preprint',
                'source': f"{enriched['source']} + {preprint.get('source', 'Preprint')}"
            })
            print(f"    [OK] Found preprint version")
            time.sleep(delay)
            return enriched
    except Exception as e:
        print(f"    Preprint search error: {e}")
    
    # Step 4: Keep original data
    print(f"    [NOT FOUND] Keeping original data (no abstract)")
    enriched['enrichment_status'] = 'original_only'
    
    time.sleep(delay)
    return enriched


def calculate_title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity between two titles (0-1 scale)."""
    t1 = title1.lower().strip()
    t2 = title2.lower().strip()
    
    for char in '.,;:?!"\'()-[]{}':
        t1 = t1.replace(char, ' ')
        t2 = t2.replace(char, ' ')
    
    words1 = set(t1.split())
    words2 = set(t2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1 & words2
    union = words1 | words2
    
    return len(intersection) / len(union)


def enrich_papers(papers: List[Dict], delay: float = 0.5) -> Tuple[List[Dict], Dict]:
    """
    Enrich a list of papers with metadata from external sources.
    
    Args:
        papers: List of paper dicts
        delay: Delay between API calls
    
    Returns:
        Tuple of (enriched_papers, statistics)
    """
    print(f"\nEnriching {len(papers)} papers...")
    print("=" * 80)
    
    enriched_papers = []
    stats = {
        'total': len(papers),
        'europepmc_doi': 0,
        'europepmc_title': 0,
        'preprint': 0,
        'original_only': 0,
        'errors': 0
    }
    
    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}/{len(papers)}]", end='')
        try:
            enriched = enrich_single_paper(paper, delay=delay)
            enriched_papers.append(enriched)
            
            status = enriched.get('enrichment_status', 'unknown')
            if status in stats:
                stats[status] += 1
            
        except Exception as e:
            print(f"  [ERROR] Failed to enrich: {e}")
            stats['errors'] += 1
            enriched_papers.append(paper)
    
    print("\n" + "=" * 80)
    print("Enrichment Summary:")
    print(f"  Total papers: {stats['total']}")
    print(f"  Europe PMC (DOI): {stats['europepmc_doi']}")
    print(f"  Europe PMC (title): {stats['europepmc_title']}")
    print(f"  Preprint servers: {stats['preprint']}")
    print(f"  Original only: {stats['original_only']}")
    print(f"  Errors: {stats['errors']}")
    
    return enriched_papers, stats


def enrich_science_papers(papers: List[Dict], delay: float = 0.5) -> Tuple[List[Dict], Dict]:
    """
    Specialized function for enriching Science journal papers.
    
    This function:
    1. Extracts DOI from Science URLs
    2. Queries Europe PMC for full metadata
    3. Falls back to preprint servers
    4. Preserves original Science metadata
    """
    print("\n" + "=" * 80)
    print("Enriching Science journal papers")
    print("=" * 80)
    
    # Add source marker
    for paper in papers:
        paper['source'] = 'Science'
        paper['original_source'] = 'Science'
    
    return enrich_papers(papers, delay=delay)


if __name__ == '__main__':
    # Test with sample data
    test_papers = [
        {
            'title': 'Highly accurate protein structure prediction with AlphaFold',
            'authors': ['Jumper J', 'Evans R'],
            'date': '15 Jul 2021',
            'url': 'https://www.science.org/doi/10.1038/s41586-021-03819-2',
            'type': 'Research Article'
        },
        {
            'title': 'Microglia Rank signaling regulates GnRH neuronal function',
            'authors': ['Collado-Sole A'],
            'date': '10 Dec 2025',
            'url': 'https://www.science.org/doi/10.1126/science.aeb6999',
            'type': 'Research Article'
        }
    ]
    
    enriched, stats = enrich_papers(test_papers, delay=1.0)
    
    print("\n" + "=" * 80)
    print("Enriched Papers:")
    print("=" * 80)
    
    for paper in enriched:
        print(f"\nTitle: {paper['title'][:70]}...")
        print(f"Status: {paper.get('enrichment_status', 'unknown')}")
        print(f"Abstract: {paper.get('abstract', 'N/A')[:100]}...")
        print(f"PMID: {paper.get('pmid', 'N/A')}")
