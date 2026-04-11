"""
Crawler for Science Advances - Section-based crawling with Selenium

Uses Selenium to fetch from Science Advances section pages:
- Neuroscience: https://www.science.org/journal/sciadv/sections?section=Neuroscience
- Biomedicine and Life Sciences: https://www.science.org/journal/sciadv/sections?section=Biomedicine%20and%20Life%20Sciences

Or from current issue TOC and filter by subject.
"""

import datetime
import time
from typing import List, Dict, Optional
import jsonlines
from bs4 import BeautifulSoup

# Section URLs to crawl
SECTION_URLS = [
    'https://www.science.org/journal/sciadv/sections?section=Neuroscience',
    'https://www.science.org/journal/sciadv/sections?section=Biomedicine%20and%20Life%20Sciences',
]

# Alternative: current issue TOC
TOC_URL = 'https://www.science.org/toc/sciadv/current'

DEFAULT_DAYS_BACK = 7


def parse_sciadv_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse Science Advances date format."""
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


def fetch_with_selenium(url: str, headless: bool = True, wait_time: int = 5) -> str:
    """
    Fetch page using Selenium to bypass anti-bot protection.
    
    Args:
        url: URL to fetch
        headless: Run browser in headless mode
        wait_time: Time to wait for page load
        
    Returns:
        HTML content
    """
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
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_window_size(1920, 1080)
    
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )
        time.sleep(wait_time)
        return driver.page_source
    finally:
        driver.quit()


def fetch_sciadv_toc(days: int = DEFAULT_DAYS_BACK, headless: bool = True) -> List[Dict]:
    """
    Fetch articles from Science Advances current TOC.
    
    Args:
        days: Number of days to look back
        headless: Use headless browser
        
    Returns:
        List of article dictionaries
    """
    url = TOC_URL
    print(f"\nFetching: {url}")
    
    try:
        html = fetch_with_selenium(url, headless=headless, wait_time=5)
        print(f"Fetched {len(html)} chars")
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find article cards - use card-header class
    articles = soup.find_all('div', class_='card-header')
    print(f"Found {len(articles)} article cards")
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    results = []
    
    for article in articles:
        try:
            # Title and URL
            title_link = article.find('a', class_='text-reset') or article.find('h3')
            if title_link and title_link.name == 'h3':
                title_link = title_link.find('a')
            
            if not title_link:
                continue
            
            title = title_link.get_text(strip=True)
            href = title_link.get('href', '')
            
            if not href or not title:
                continue
            
            article_url = f"https://www.science.org{href}" if href.startswith('/') else href
            
            # Extract DOI
            doi = ''
            if '/doi/' in href:
                doi_part = href.split('/doi/')[-1].split('?')[0].split('#')[0]
                if doi_part.startswith('10.'):
                    doi = doi_part
            
            # Authors - look for comma-separated list
            authors = []
            author_list = article.find('ul', class_='comma-separated')
            if author_list:
                author_items = author_list.find_all('li', class_='list-inline-item')
                for item in author_items:
                    name_span = item.find('span')
                    if name_span:
                        name = name_span.get_text(strip=True)
                        if name and name not in authors:
                            authors.append(name)
            
            # Date
            date_elem = article.find('time')
            date_str = ''
            if date_elem:
                date_str = date_elem.get_text(strip=True)
                if not date_str:
                    date_str = date_elem.get('datetime', '')
            
            # Alternative: look for date pattern in text
            if not date_str:
                date_span = article.find('span', class_='date')
                if date_span:
                    date_str = date_span.get_text(strip=True)
            
            # Parse date for filtering
            article_date = parse_sciadv_date(date_str)
            if article_date and article_date < cutoff_date:
                continue
            
            # Format date
            if article_date:
                date_formatted = article_date.strftime('%d %b %Y')
            else:
                date_formatted = date_str
            
            # Article type
            type_elem = article.find('span', class_='overline')
            article_type = type_elem.get_text(strip=True) if type_elem else 'Article'
            
            results.append({
                'type': article_type,
                'title': title,
                'authors': authors,
                'date': date_formatted,
                'url': article_url,
                'doi': doi,
                'abstract': '',
                'source': 'Science Advances'
            })
            
        except Exception as e:
            print(f"[WARN] Parse error: {e}")
            continue
    
    print(f"Extracted {len(results)} articles from this section")
    return results


def fetch_sciadv_papers(days: int = DEFAULT_DAYS_BACK,
                        max_results: int = 200,
                        enrich: bool = True,
                        delay: float = 0.5,
                        headless: bool = True) -> List[Dict]:
    """
    Fetch papers from Science Advances TOC and filter by date.
    
    Note: Science Advances website doesn't have separate section pages that work
    reliably. We fetch from the current TOC and filter by date.
    
    Args:
        days: Number of days to look back
        max_results: Maximum results
        enrich: Whether to enrich with Europe PMC
        delay: Delay between enrichment requests
        headless: Use headless browser
        
    Returns:
        List of paper dictionaries
    """
    print("=" * 80)
    print(f"Fetching from Science Advances (last {days} days)...")
    print("Note: Using TOC page and filtering by date")
    print("=" * 80)
    
    all_papers = fetch_sciadv_toc(days=days, headless=headless)
    
    print(f"\nTotal papers from Science Advances TOC: {len(all_papers)}")
    
    unique_papers = all_papers
    
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


def save_sciadv_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/sciadv_{timestamp}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


# ============== Test Functions ==============

def test_fetch():
    """Test fetching papers from Science Advances."""
    print("\n" + "=" * 80)
    print("Testing Science Advances Crawler (Section-based)")
    print("=" * 80)
    
    # Test with last 7 days, no enrichment for speed
    papers = fetch_sciadv_papers(days=7, enrich=False, headless=True)
    
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
        
        # Save results
        save_sciadv_papers(papers, "getfiles/sciadv_test.jsonl")
    else:
        print("\nNo papers found.")
    
    return papers


if __name__ == '__main__':
    test_fetch()
