"""
Cell Press Journal Crawler

Supports multiple Cell Press journals:
- Cell
- Neuron
- Current Biology
- Trends in Neurosciences
- Cell Reports
- iScience
- Cell Systems
- and more...

Strategy:
1. Fetch list pages using Selenium (bypass Cloudflare)
2. Extract basic info: title, authors, date, DOI, URL
3. Enrich with Europe PMC for abstracts
4. Fallback to preprint servers
"""
import time
import datetime
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
import jsonlines
from dateutil import parser

# Import enrichment module
try:
    from enrich_papers import enrich_papers
except ImportError:
    from src.enrich_papers import enrich_papers


# Cell Press journal configurations
CELL_JOURNALS = {
    'cell': {
        'name': 'Cell',
        'url': 'https://www.cell.com/cell/current',
        'selector': 'h2.article-title',
    },
    'neuron': {
        'name': 'Neuron',
        'url': 'https://www.cell.com/neuron/current',
        'selector': '.toc__item h3',
    },
    'current-biology': {
        'name': 'Current Biology',
        'url': 'https://www.cell.com/current-biology/current',
        'selector': '.toc__item h3',
        'note': 'May be blocked by Cloudflare - will skip if unavailable'
    },
    'trends-neurosciences': {
        'name': 'Trends in Neurosciences',
        'url': 'https://www.cell.com/trends/neurosciences/current',
        'selector': '.toc__item h3',
    },
    # 'cell-reports': {
    #     'name': 'Cell Reports',
    #     'url': 'https://www.cell.com/cell-reports/current',
    #     'selector': '.toc__item h3',
    # },
    # 'iscience': {
    #     'name': 'iScience',
    #     'url': 'https://www.cell.com/iscience/current',
    #     'selector': '.toc__item h3',
    # },
    # 'cell-systems': {
    #     'name': 'Cell Systems',
    #     'url': 'https://www.cell.com/cell-systems/current',
    #     'selector': '.toc__item h3',
    # },
}


def extract_doi_from_cell_url(url: str) -> Optional[str]:
    """Extract DOI from Cell Press URL using PII."""
    if not url:
        return None
    
    import re
    
    # Cell Press URLs contain PII like: S0896-6273(26)00091-7
    # We can convert PII to DOI format
    pii_match = re.search(r'[AS](\d{4})-(\d{4})\((\d{2})\)([\w\d.-]+)', url)
    if pii_match:
        # PII format: S0896-6273(26)00091-7
        # DOI format: 10.1016/j.neuron.2026.00091 (approximate)
        # This is a simplification - actual DOI may vary by journal
        prefix = pii_match.group(1) + pii_match.group(2)
        year = pii_match.group(3)
        suffix = pii_match.group(4).replace('-', '')
        
        # Map journal prefixes
        journal_map = {
            '08966273': 'neuron',
            '00928674': 'cell',
            '09609822': 'cub',
            '01662236': 'tins',
            '22111247': 'celrep',
            '25890042': 'isci',
            '24054712': 'cels',
        }
        
        journal_code = journal_map.get(prefix, 'cell')
        return f"10.1016/j.{journal_code}.20{year}.{suffix[:5]}"
    
    return None


def parse_cell_date(date_str: str) -> str:
    """Parse various Cell Press date formats."""
    try:
        # Try common formats
        # "20 Mar 2026" or "March 20, 2026" or "2026-03-20"
        dt = parser.parse(date_str)
        return dt.strftime('%d %b %Y')
    except:
        return date_str


def fetch_journal_list(journal_key: str, headless: bool = True, timeout: int = 30) -> Tuple[List[Dict], str]:
    """
    Fetch article list from a Cell Press journal.
    
    Args:
        journal_key: Key from CELL_JOURNALS
        headless: Use headless browser
        timeout: Page load timeout
        
    Returns:
        Tuple of (articles list, journal name)
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    if journal_key not in CELL_JOURNALS:
        raise ValueError(f"Unknown journal: {journal_key}. Available: {list(CELL_JOURNALS.keys())}")
    
    config = CELL_JOURNALS[journal_key]
    url = config['url']
    selector = config['selector']
    journal_name = config['name']
    
    print(f"=" * 80)
    print(f"Cell Press Crawler - {journal_name}")
    print(f"=" * 80)
    print(f"Fetching: {url}")
    
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    from selenium.webdriver.chrome.service import Service
    # 使用 Service 对象（新版 Selenium 推荐）
    # service = Service()
    # 替换原来的 driver = webdriver.Chrome(...)
    from webdriver_manager.chrome import ChromeDriverManager
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(timeout)
    
    articles = []
    
    try:
        # Load page
        driver.get(url)
        
        # Wait for content to load
        time.sleep(5)
        
        html = driver.page_source
        print(f"Fetched {len(html)} chars via Selenium")
        
        # Check for blocking
        if 'challenge-error-text' in html or 'cf-chl' in html:
            print("[ERROR] Cloudflare challenge detected!")
            return [], journal_name
        
        if 'captcha' in html.lower():
            print("[ERROR] CAPTCHA detected!")
            return [], journal_name
        
        # Parse HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find article elements - use .toc__item which contains each article
        article_elements = soup.select('.toc__item')
        
        if not article_elements:
            print("[WARNING] No article elements found with .toc__item")
            # Fallback to other selectors
            selectors_to_try = ['article', '.article-in-issue', '[class*="article"]']
            for sel in selectors_to_try:
                article_elements = soup.select(sel)
                if article_elements:
                    print(f"Found {len(article_elements)} elements with selector: {sel}")
                    break
        else:
            print(f"Found {len(article_elements)} article elements with .toc__item")
        
        if not article_elements:
            print("[WARNING] No article elements found")
            return [], journal_name
        
        # Extract article info
        for elem in article_elements:
            try:
                # Skip if no data-pii (not a real article)
                if not elem.get('data-pii'):
                    continue
                
                # Title - look for .toc__item__title or h3
                title_elem = elem.select_one('.toc__item__title')
                if not title_elem:
                    title_elem = elem.find('h3')
                
                if not title_elem:
                    continue
                
                # Get title text from the link or the element itself
                title_link = title_elem.find('a')
                if title_link:
                    title = title_link.get_text(strip=True)
                    href = title_link.get('href', '')
                else:
                    title = title_elem.get_text(strip=True)
                    # Try to find any link in the element
                    any_link = elem.find('a', href=True)
                    href = any_link.get('href', '') if any_link else ''
                
                if not title or len(title) < 10:
                    continue
                
                # Skip non-article items
                skip_keywords = ['advisory board', 'contents', 'editorial board', 'masthead', 
                               'corrigendum', 'retraction', 'in this issue', 'preview']
                if any(keyword in title.lower() for keyword in skip_keywords):
                    continue
                
                # Build full URL
                if href.startswith('/'):
                    article_url = f"https://www.cell.com{href}"
                elif href.startswith('http'):
                    article_url = href
                else:
                    article_url = f"https://www.cell.com/{href}"
                
                # Authors - look for .toc__item__authors .loa__item
                author_elems = elem.select('.toc__item__authors .loa__item')
                if author_elems:
                    authors = [a.get_text(strip=True).rstrip(',') for a in author_elems]
                else:
                    authors = []
                
                # Brief/Abstract - look for .toc__item__brief
                brief_elem = elem.select_one('.toc__item__brief')
                brief = brief_elem.get_text(strip=True) if brief_elem else ''
                
                # Date - Cell Press list pages often don't show dates
                # We'll use current date as fallback, or try to extract from page
                date_elem = elem.find('time')
                if date_elem:
                    date_str = date_elem.get_text(strip=True)
                    date = parse_cell_date(date_str)
                else:
                    # Use current date as fallback
                    date = datetime.datetime.now().strftime('%d %b %Y')
                
                # Article type - try to determine from context
                # Check if it looks like a research article
                article_type = 'Article'
                
                # Extract DOI from URL
                doi = extract_doi_from_cell_url(article_url)
                
                articles.append({
                    'type': article_type,
                    'title': title,
                    'authors': authors,
                    'date': date,
                    'url': article_url,
                    'doi': doi or '',
                    'abstract': brief,  # Use brief as initial abstract
                    'source': journal_name,
                })
                
            except Exception as e:
                print(f"Parse error: {e}")
                continue
        
        print(f"Extracted {len(articles)} research articles")
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch: {e}")
    finally:
        driver.quit()
    
    return articles, journal_name


def filter_by_date(articles: List[Dict], days: int = 7) -> List[Dict]:
    """
    Filter articles by publication date.
    
    Args:
        articles: List of article dicts
        days: Number of days to look back
        
    Returns:
        Filtered list of articles
    """
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.now() - timedelta(days=days)
    filtered = []
    
    for article in articles:
        try:
            article_date = parser.parse(article['date'])
            if article_date >= cutoff_date:
                filtered.append(article)
        except:
            # If date parsing fails, include the article
            filtered.append(article)
    
    return filtered


def fetch_cell_papers(
    journals: Optional[List[str]] = None,
    days: Optional[int] = None,
    enrich: bool = True,
    delay: float = 0.5,
    headless: bool = True
) -> List[Dict]:
    """
    Fetch papers from Cell Press journals.
    
    Args:
        journals: List of journal keys to fetch (None = all)
        days: Filter by last N days (None = no filter)
        enrich: Whether to enrich with Europe PMC
        delay: Delay between enrichment requests
        headless: Use headless browser
        
    Returns:
        List of paper dicts
    """
    if journals is None:
        journals = ['neuron', 'current-biology', 'trends-neurosciences']
    
    all_articles = []
    
    for journal_key in journals:
        try:
            articles, journal_name = fetch_journal_list(journal_key, headless=headless)
            all_articles.extend(articles)
            
            # Small delay between journals
            if len(journals) > 1:
                time.sleep(2)
                
        except Exception as e:
            print(f"[ERROR] Failed to fetch {journal_key}: {e}")
            continue
    
    # Filter by date if specified
    if days:
        all_articles = filter_by_date(all_articles, days)
        print(f"\nFiltered to {len(all_articles)} articles from last {days} days")
    
    # Enrich with Europe PMC
    if enrich and all_articles:
        print("\n" + "=" * 80)
        print("Enriching with Europe PMC...")
        print("=" * 80)
        enriched, stats = enrich_papers(all_articles, delay=delay)
        return enriched
    
    return all_articles


def save_cell_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to JSONL file."""
    if filepath is None:
        filepath = f"getfiles/cell-press-{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    return filepath


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Cell Press journal crawler')
    parser.add_argument('--journals', nargs='+', default=['neuron', 'current-biology'],
                        help='Journals to fetch (default: neuron current-biology)')
    parser.add_argument('--days', type=int, default=None,
                        help='Filter by last N days')
    parser.add_argument('--no-enrich', action='store_true',
                        help='Skip Europe PMC enrichment')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between enrichment requests (default: 0.5s)')
    parser.add_argument('--list-journals', action='store_true',
                        help='List available journals')
    
    args = parser.parse_args()
    
    if args.list_journals:
        print("Available Cell Press journals:")
        for key, config in CELL_JOURNALS.items():
            print(f"  {key}: {config['name']} ({config['url']})")
        exit(0)
    
    # Fetch papers
    papers = fetch_cell_papers(
        journals=args.journals,
        days=args.days,
        enrich=not args.no_enrich,
        delay=args.delay
    )
    
    if papers:
        # Save
        filepath = save_cell_papers(papers)
        print(f"\nSaved {len(papers)} papers to: {filepath}")
        
        # Summary
        if not args.no_enrich:
            status_counts = {}
            for p in papers:
                status = p.get('enrichment_status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            print("\nEnrichment summary:")
            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")
        
        # Show samples
        print("\nSample papers:")
        for p in papers[:3]:
            print(f"\n- {p['title'][:70]}...")
            print(f"  Date: {p['date']}, Source: {p.get('source', 'N/A')}")
            if p.get('abstract'):
                print(f"  Abstract: {p['abstract'][:100]}...")
    else:
        print("No papers found")
