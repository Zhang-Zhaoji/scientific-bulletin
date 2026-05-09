"""
Science Journal Crawler (Beta with Scrapling)

Strategy (Updated 2026-05-09):
1. Primary: Scrapling StealthyFetcher to bypass Cloudflare
2. Fallback: PubMed API for journal "Science" if web scraping fails

Note: science.org uses Cloudflare managed challenge. Scrapling's StealthyFetcher
uses a hardened Firefox (Camoufox) that bypasses most protections out-of-the-box.
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


def _fetch_with_scrapling(url: str, headless: bool = True, wait: int = 8) -> Optional[str]:
    """Fetch page using Scrapling StealthyFetcher to bypass Cloudflare."""
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        print("[WARN] Scrapling not installed. Run: pip install scrapling")
        return None

    try:
        print(f"Fetching with Scrapling StealthyFetcher (headless={headless})...")
        page = StealthyFetcher.fetch(url, headless=headless)
        html = page.body.decode('utf-8')
        print(f"Fetched {len(html)} chars via Scrapling")
        return html
    except Exception as e:
        print(f"Scrapling failed: {e}")
        return None


def _fetch_science_from_web(headless: bool = True, days: Optional[int] = None) -> List[Dict]:
    """Internal: fetch from science.org via Scrapling."""
    url = 'https://www.science.org/journal/science/research?startPage=0&pageSize=100'
    print(f"Fetching: {url}")

    html = _fetch_with_scrapling(url, headless=headless, wait=10)

    if not html:
        return []

    # Parse HTML
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.find_all('div', class_='card-header')
    print(f"Found {len(cards)} article cards")

    if not cards:
        return []

    articles = []
    cutoff_date = None
    if days:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        print(f"Filtering: only articles from last {days} days (after {cutoff_date.date()})")

    for card in cards:
        try:
            title_elem = card.find('a', class_='text-reset animation-underline')
            if not title_elem:
                continue

            title = title_elem.text.strip()
            href = title_elem.get('href', '')
            doi = extract_doi_from_url(href)
            article_url = f"https://www.science.org{href}" if href.startswith('/') else href

            author_elems = card.find_all('span', class_='hlFld-ContribAuthor')
            authors = [a.text.strip() for a in author_elems]

            date_elem = card.find('time')
            date_str = date_elem.text.strip() if date_elem else 'No date'

            if days and cutoff_date:
                try:
                    article_date = None
                    for fmt in ['%d %b %Y', '%b %d %Y', '%Y-%m-%d']:
                        try:
                            article_date = datetime.datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    if article_date and article_date < cutoff_date:
                        continue
                except Exception as e:
                    print(f"Date parse warning: {date_str} - {e}")

            type_elem = card.find('span', class_='overline')
            article_type = type_elem.text.strip() if type_elem else 'Article'

            if article_type not in ['Research Article', 'Report', 'Review Article', 'Brevia']:
                continue

            articles.append({
                'type': article_type,
                'title': title,
                'authors': authors,
                'date': date_str,
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


def _fetch_science_from_pubmed(days: Optional[int] = None) -> List[Dict]:
    """Internal: fallback via PubMed API."""
    print("\n" + "=" * 80)
    print("Falling back to PubMed API for Science journal")
    print("=" * 80)

    try:
        from crawler_pubmed import fetch_articles_by_journal
    except ImportError:
        print("PubMed crawler not available")
        return []

    papers = fetch_articles_by_journal(
        journal_name='Science',
        days=days or 14,
        max_results=100,
        fetch_abstracts=False,
        exclude_types=['Erratum', 'Correction', 'Retraction', 'Editorial']
    )

    normalized = []
    for p in papers:
        doi = p.get('doi', '')
        url = f"https://www.science.org/doi/{doi}" if doi else p.get('pubmed_url', '')
        normalized.append({
            'type': p.get('type', 'Article'),
            'title': p.get('title', ''),
            'authors': p.get('authors', []),
            'date': p.get('date', ''),
            'url': url,
            'doi': doi,
            'pmid': p.get('pmid', ''),
            'abstract': p.get('abstract', ''),
            'source': 'Science'
        })

    print(f"Extracted {len(normalized)} research articles from PubMed")
    return normalized


def fetch_science_list(headless: bool = True, days: Optional[int] = None) -> List[Dict]:
    """
    Fetch Science articles.

    Args:
        headless: Run browser headless (StealthyFetcher default is True)
        days: Only return articles from last N days (None = no filter)

    Returns:
        List of article dicts with basic info
    """
    print("=" * 80)
    print("Science Crawler (Scrapling Beta)")
    print("=" * 80)

    articles = _fetch_science_from_web(headless=headless, days=days)

    if not articles:
        print("Web scraping returned no articles; trying PubMed fallback...")
        articles = _fetch_science_from_pubmed(days=days)

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
    articles = fetch_science_list(days=days)

    if not articles or not enrich:
        return articles

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

    parser = argparse.ArgumentParser(description='Science journal crawler (Scrapling Beta)')
    parser.add_argument('--no-enrich', action='store_true',
                        help='Skip Europe PMC enrichment')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between enrichment requests (default: 0.5s)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Run browser in visible mode (default: headless)')
    parser.add_argument('--days', type=int, default=None,
                        help='Only fetch articles from last N days')
    args = parser.parse_args()

    papers = fetch_science_papers(
        enrich=not args.no_enrich,
        delay=args.delay,
        days=args.days
    )

    if papers:
        filepath = save_science_papers(papers)
        print(f"\nSaved {len(papers)} papers to: {filepath}")

        if not args.no_enrich:
            status_counts = {}
            for p in papers:
                status = p.get('enrichment_status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1

            print("\nEnrichment summary:")
            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")

        print("\nSample papers:")
        for p in papers[:3]:
            print(f"\n- {p['title'][:70]}...")
            print(f"  Date: {p['date']}, DOI: {p.get('doi', 'N/A')[:30]}...")
            if p.get('abstract'):
                print(f"  Abstract: {p['abstract'][:100]}...")
    else:
        print("No papers found")
