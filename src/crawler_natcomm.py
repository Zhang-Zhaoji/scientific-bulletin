"""
Crawler for Nature Communications - Subject-based crawling

Uses requests to fetch from Nature Communications subject pages:
- Biological Sciences: https://www.nature.com/subjects/biological-sciences/ncomms
- Health Sciences: https://www.nature.com/subjects/health-sciences/ncomms

This avoids non-biology articles like pure chemistry, physics, materials science.
"""

import requests
import datetime
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import jsonlines

# Subject URLs to crawl
SUBJECT_URLS = [
    'https://www.nature.com/subjects/biological-sciences/ncomms',
    'https://www.nature.com/subjects/health-sciences/ncomms',
]

DEFAULT_DAYS_BACK = 7


def parse_natcomm_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse Nature Communications date format."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    formats = [
        '%d %B %Y',      # 10 April 2026
        '%d %b %Y',      # 10 Apr 2026
        '%B %d, %Y',     # April 10, 2026
        '%b %d, %Y',     # Apr 10, 2026
        '%Y-%m-%d',      # 2026-04-10
    ]
    
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def fetch_natcomm_subject_page(url: str, days: int = DEFAULT_DAYS_BACK) -> List[Dict]:
    """
    Fetch articles from a Nature Communications subject page.
    
    Args:
        url: Subject page URL
        days: Number of days to look back
        
    Returns:
        List of article dictionaries
    """
    print(f"\nFetching: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all article elements
    articles = soup.find_all('article')
    print(f"Found {len(articles)} article elements")
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    results = []
    
    for article in articles:
        try:
            # Title and URL - look for h3 > a structure
            title_elem = article.find('h3')
            if not title_elem:
                continue
            
            title_link = title_elem.find('a', href=True)
            if not title_link:
                continue
            
            title = title_link.get_text(strip=True)
            href = title_link.get('href', '')
            
            if not href:
                continue
            
            article_url = f"https://www.nature.com{href}" if href.startswith('/') else href
            
            # Extract DOI from URL
            doi = ''
            if '/articles/' in href:
                doi_part = href.split('/articles/')[-1].split('?')[0].split('#')[0]
                if doi_part:
                    doi = f"10.1038/{doi_part}"
            
            # Authors - look for author list
            author_list = article.find('ul', {'data-test': 'author-list'})
            authors = []
            if author_list:
                author_items = author_list.find_all('li', itemprop='creator')
                for item in author_items:
                    name_elem = item.find('span', itemprop='name')
                    if name_elem:
                        authors.append(name_elem.get_text(strip=True))
            
            # Date - look for time element
            date_elem = article.find('time', datetime=True)
            date_str = ''
            if date_elem:
                # Use datetime attribute (ISO format)
                date_str = date_elem.get('datetime', '')
                if not date_str:
                    date_str = date_elem.get_text(strip=True)
            
            # Parse date for filtering
            article_date = parse_natcomm_date(date_str)
            if article_date and article_date < cutoff_date:
                continue  # Skip old articles
            
            # Format date
            if article_date:
                date_formatted = article_date.strftime('%d %b %Y')
            else:
                date_formatted = date_str
            
            # Article type
            type_elem = article.find('span', {'data-test': 'article.type'})
            article_type = type_elem.get_text(strip=True) if type_elem else 'Article'
            
            results.append({
                'type': article_type,
                'title': title,
                'authors': authors,
                'date': date_formatted,
                'url': article_url,
                'doi': doi,
                'abstract': '',
                'source': 'Nature Communications'
            })
            
        except Exception as e:
            print(f"[WARN] Parse error: {e}")
            continue
    
    print(f"Extracted {len(results)} articles from this subject")
    return results


def fetch_natcomm_papers(days: int = DEFAULT_DAYS_BACK,
                         max_results: int = 200,
                         enrich: bool = True,
                         delay: float = 0.5) -> List[Dict]:
    """
    Fetch papers from Nature Communications subject pages.
    
    Args:
        days: Number of days to look back
        max_results: Maximum results per subject
        enrich: Whether to enrich with Europe PMC
        delay: Delay between enrichment requests
        
    Returns:
        List of paper dictionaries
    """
    print("=" * 80)
    print(f"Fetching from Nature Communications (last {days} days)...")
    print("Sources: Biological Sciences, Health Sciences")
    print("=" * 80)
    
    all_papers = []
    
    for url in SUBJECT_URLS:
        papers = fetch_natcomm_subject_page(url, days=days)
        all_papers.extend(papers)
        time.sleep(1)  # Be polite
    
    # Deduplicate by DOI or title
    seen = set()
    unique_papers = []
    for paper in all_papers:
        key = paper.get('doi') or paper['title'].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique_papers.append(paper)
    
    print(f"\nTotal unique papers from Nature Communications: {len(unique_papers)}")
    
    # Enrich with Europe PMC if requested
    if enrich and unique_papers:
        print("\n" + "=" * 80)
        print("Enriching with Europe PMC...")
        print("=" * 80)
        
        from enrich_papers import enrich_papers
        enriched, stats = enrich_papers(unique_papers, delay=delay)
        
        print(f"\nEnrichment complete:")
        for status, count in sorted(stats.items()):
            print(f"  {status}: {count}")
        
        return enriched
    
    return unique_papers


def save_natcomm_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/natcomm_{timestamp}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


# ============== Test Functions ==============

def test_fetch():
    """Test fetching papers from Nature Communications."""
    print("\n" + "=" * 80)
    print("Testing Nature Communications Crawler (Subject-based)")
    print("=" * 80)
    
    # Test with last 7 days
    papers = fetch_natcomm_papers(days=7, enrich=True)
    
    if papers:
        print("\n" + "=" * 80)
        print("Sample Papers:")
        print("=" * 80)
        for i, paper in enumerate(papers[:5], 1):
            print(f"\n[{i}] {paper['title']}")
            print(f"    Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
            print(f"    Date: {paper['date']}")
            print(f"    Type: {paper['type']}")
            print(f"    DOI: {paper.get('doi', 'N/A')}")
            if paper.get('abstract'):
                print(f"    Abstract: {paper['abstract'][:100]}...")
        
        # Save results
        save_natcomm_papers(papers, "getfiles/natcomm_test.jsonl")
    else:
        print("\nNo papers found.")
    
    return papers


if __name__ == '__main__':
    test_fetch()
