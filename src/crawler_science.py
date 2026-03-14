"""
Science Journal Crawler

Strategy:
1. Fetch list pages (basic info: title, authors, date, DOI)
2. Enrich with Europe PMC (abstracts, PMIDs)
3. Fallback to preprint servers for very recent articles

This avoids captcha issues by not accessing individual article pages.
"""
import requests
import datetime
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import jsonlines
from utils import normalize_url, select_articles


def extract_doi_from_url(url: str) -> Optional[str]:
    """Extract DOI from Science URL."""
    if not url:
        return None
    if '/doi/' in url:
        doi = url.split('/doi/')[-1].split('?')[0].split('#')[0].strip('/')
        return doi if doi.startswith('10.') else None
    return None


def fetch_science_list(use_requests: bool = False, headless: bool = True, days: Optional[int] = None) -> List[Dict]:
    """
    Fetch Science articles from list pages.
    
    Args:
        use_requests: Use requests instead of Selenium (faster, but may miss JS content)
        headless: Use headless browser if Selenium is used
        days: Only return articles from last N days (None = no filter)
    
    Returns:
        List of article dicts with basic info
    """
    print("=" * 80)
    print("Science Crawler - List Pages Only")
    print("=" * 80)
    
    url = 'https://www.science.org/journal/science/research?startPage=0&pageSize=100'
    print(f"Fetching: {url}")
    
    if use_requests:
        # Fast method using requests
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            html = response.text
            print(f"Fetched {len(html)} chars via requests")
        except Exception as e:
            print(f"Requests failed: {e}, falling back to Selenium...")
            use_requests = False
    
    if not use_requests:
        # Fallback to Selenium
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_window_size(1920, 1080)
        
        try:
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            time.sleep(3)
            html = driver.page_source
            print(f"Fetched {len(html)} chars via Selenium")
        finally:
            driver.quit()
    
    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.find_all('div', class_='card-header')
    print(f"Found {len(cards)} article cards")
    
    articles = []
    cutoff_date = None
    if days:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        print(f"Filtering: only articles from last {days} days (after {cutoff_date.date()})")
    for card in cards:
        try:
            # Title & URL
            title_elem = card.find('a', class_='text-reset animation-underline')
            if not title_elem:
                continue
            
            title = title_elem.text.strip()
            href = title_elem.get('href', '')
            
            # DOI
            doi = extract_doi_from_url(href)
            
            # Full URL
            article_url = f"https://www.science.org{href}" if href.startswith('/') else href
            
            # Authors
            author_elems = card.find_all('span', class_='hlFld-ContribAuthor')
            authors = [a.text.strip() for a in author_elems]
            
            # Date
            date_elem = card.find('time')
            date = date_elem.text.strip() if date_elem else 'No date'
            date_str = date_elem.text.strip() if date_elem else 'No date'
            
            if days and cutoff_date:
                try:
                    # Science 日期格式通常是 "13 Mar 2026" 或 "Mar 13 2026"
                    article_date = None
                    for fmt in ['%d %b %Y', '%b %d %Y', '%Y-%m-%d']:
                        try:
                            article_date = datetime.datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if article_date and article_date < cutoff_date:
                        continue  # 跳过过期文章
                        
                except Exception as e:
                    print(f"Date parse warning: {date_str} - {e}")
            
            # Type
            type_elem = card.find('span', class_='overline')
            article_type = type_elem.text.strip() if type_elem else 'Article'
            
            # Filter
            if article_type not in ['Research Article', 'Report', 'Review Article', 'Brevia']:
                continue
            
            articles.append({
                'type': article_type,
                'title': title,
                'authors': authors,
                'date': date,
                'url': article_url,
                'doi': doi or '',
                'abstract': '',
                'source': 'Science'
            })
            
        except Exception as e:
            print(f"Parse error: {e}")
            continue
    
    print(f"Extracted {len(articles)} research articles")
    return articles


def fetch_science_papers(enrich: bool = True, delay: float = 0.5, days: Optional[int] = None) -> List[Dict]:
    """
    Fetch Science papers with optional Europe PMC enrichment.
    
    Args:
        enrich: Whether to enrich with Europe PMC
        delay: Delay between enrichment requests
        days: Only return articles from last N days
    
    Returns:
        List of paper dicts
    """
    # Step 1: Get basic info (带日期筛选)
    articles = fetch_science_list(days=days)
    
    if not articles or not enrich:
        return articles
    
    # Step 2: Enrich
    print("\n" + "=" * 80)
    print("Enriching with Europe PMC and preprint servers...")
    print("=" * 80)
    
    from enrich_papers import enrich_science_papers
    enriched, stats = enrich_science_papers(articles, delay=delay)
    
    return enriched


def save_science_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to JSONL file."""
    if filepath is None:
        filepath = f"getfiles/science-{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    return filepath


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Science journal crawler')
    parser.add_argument('--no-enrich', action='store_true',
                        help='Skip Europe PMC enrichment')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between enrichment requests (default: 0.5s)')
    parser.add_argument('--selenium', action='store_true',
                        help='Use Selenium instead of requests')
    args = parser.parse_args()
    
    # Fetch papers
    papers = fetch_science_papers(enrich=not args.no_enrich, delay=args.delay)
    
    if papers:
        # Save
        filepath = save_science_papers(papers)
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
            print(f"  Date: {p['date']}, DOI: {p.get('doi', 'N/A')[:30]}...")
            if p.get('abstract'):
                print(f"  Abstract: {p['abstract'][:100]}...")
    else:
        print("No papers found")