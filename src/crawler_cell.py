"""
Cell Press Journal Crawler (Beta with Scrapling)

Supports multiple Cell Press journals:
- Cell
- Neuron
- Current Biology
- Trends in Neurosciences
- Cell Reports
- iScience
- Cell Systems
- and more...

Strategy (Updated 2026-05-09):
1. Fetch list pages using Scrapling StealthyFetcher (bypass Cloudflare)
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
import requests

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
        'pubmed_name': 'Cell',
        'europepmc_journal': 'Cell',
    },
    'neuron': {
        'name': 'Neuron',
        'url': 'https://www.cell.com/neuron/current',
        'selector': '.toc__item h3',
        'pubmed_name': 'Neuron',
        'europepmc_journal': 'Neuron',
    },
    'current-biology': {
        'name': 'Current Biology',
        'url': 'https://www.cell.com/current-biology/current',
        'selector': '.toc__item h3',
        'note': 'May be blocked by Cloudflare - will use PubMed/Europe PMC fallback if unavailable',
        'pubmed_name': 'Current Biology',
        'europepmc_journal': 'Current Biology',
    },
    'trends-neurosciences': {
        'name': 'Trends in Neurosciences',
        'url': 'https://www.cell.com/trends/neurosciences/current',
        'selector': '.toc__item h3',
        'pubmed_name': 'Trends Neurosci',
        'europepmc_journal': 'Trends in Neurosciences',
    },
    # 'cell-reports': {
    #     'name': 'Cell Reports',
    #     'url': 'https://www.cell.com/cell-reports/current',
    #     'selector': '.toc__item h3',
    #     'pubmed_name': 'Cell Reports',
    #     'europepmc_journal': 'Cell Reports',
    # },
    'iscience': {
        'name': 'iScience',
        'url': 'https://www.cell.com/iscience/current',
        'selector': '.toc__item h3',
        'pubmed_name': 'iScience',
        'europepmc_journal': 'iScience',
    },
    # 'cell-systems': {
    #     'name': 'Cell Systems',
    #     'url': 'https://www.cell.com/cell-systems/current',
    #     'selector': '.toc__item h3',
    #     'pubmed_name': 'Cell Systems',
    #     'europepmc_journal': 'Cell Systems',
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


def _fetch_with_scrapling(url: str, headless: bool = True) -> Optional[str]:
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


def _normalize_journal_name(name: str) -> str:
    """Normalize journal names for loose comparisons."""
    return ' '.join((name or '').lower().replace('&', 'and').split())


def _normalize_fallback_article(paper: Dict, journal_name: str, fallback_source: str) -> Dict:
    """Convert PubMed/Europe PMC records into the Cell crawler schema."""
    doi = paper.get('doi', '') or ''
    pubmed_url = paper.get('pubmed_url', '') or (
        f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('pmid')}/" if paper.get('pmid') else ''
    )
    url = paper.get('doi_url') or paper.get('url') or pubmed_url

    normalized = {
        'type': paper.get('type', 'Article'),
        'title': paper.get('title', ''),
        'authors': paper.get('authors', []),
        'date': paper.get('date', ''),
        'url': url,
        'doi': doi,
        'abstract': paper.get('abstract', ''),
        'source': journal_name,
        'journal': paper.get('journal', journal_name) or journal_name,
        'retrieval_source': fallback_source,
    }

    for key in ['pmid', 'pmcid', 'journal_volume', 'journal_issue', 'page_info',
                'doi_url', 'pubmed_url', 'is_open_access', 'pub_type']:
        if paper.get(key):
            normalized[key] = paper[key]

    return normalized


def _fetch_journal_from_pubmed(journal_key: str, days: Optional[int], max_results: int = 100) -> List[Dict]:
    """Fallback: fetch recent Cell Press articles through PubMed."""
    config = CELL_JOURNALS[journal_key]
    journal_name = config['name']
    pubmed_name = config.get('pubmed_name', journal_name)
    fallback_days = days or 14

    print("\n" + "=" * 80)
    print(f"Falling back to PubMed API for {journal_name}")
    print("=" * 80)

    try:
        try:
            from crawler_pubmed import fetch_articles_by_journal
        except ImportError:
            from src.crawler_pubmed import fetch_articles_by_journal

        papers = fetch_articles_by_journal(
            journal_name=pubmed_name,
            days=fallback_days,
            max_results=max_results,
            fetch_abstracts=False,
            exclude_types=[
                'Erratum', 'Correction', 'Retraction', 'Editorial',
                'News', 'Comment', 'Letter', 'Preview'
            ]
        )
    except Exception as e:
        print(f"[ERROR] PubMed fallback failed for {journal_name}: {e}")
        return []

    normalized = [
        _normalize_fallback_article(paper, journal_name, 'PubMed fallback')
        for paper in papers
    ]
    print(f"Extracted {len(normalized)} articles from PubMed for {journal_name}")
    return normalized


def _fetch_journal_from_europepmc(journal_key: str, days: Optional[int], max_results: int = 100) -> List[Dict]:
    """Fallback: fetch recent Cell Press articles through Europe PMC/PMC."""
    config = CELL_JOURNALS[journal_key]
    journal_name = config['name']
    europepmc_journal = config.get('europepmc_journal', journal_name)
    fallback_days = days or 14

    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=fallback_days)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    print("\n" + "=" * 80)
    print(f"Falling back to Europe PMC/PMC for {journal_name}")
    print("=" * 80)

    try:
        try:
            from crawler_europepmc import EUROPEPMC_API_URL, parse_europepmc_result
        except ImportError:
            from src.crawler_europepmc import EUROPEPMC_API_URL, parse_europepmc_result

        query = f'JOURNAL:"{europepmc_journal}" AND FIRST_PDATE:[{start_str} TO {end_str}]'
        params = {
            'query': query,
            'resultType': 'core',
            'format': 'json',
            'pageSize': max_results,
            'sort': 'FIRST_PDATE_D desc'
        }
        print(f"Europe PMC query: {query}")

        response = requests.get(f"{EUROPEPMC_API_URL}/search", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"[ERROR] Europe PMC fallback failed for {journal_name}: {e}")
        return []

    result_list = data.get('resultList', {}).get('result', [])
    target_journal = _normalize_journal_name(journal_name)
    normalized = []

    for result in result_list:
        parsed = parse_europepmc_result(result)
        if not parsed:
            continue

        result_journal = _normalize_journal_name(parsed.get('journal', ''))
        if result_journal and result_journal != target_journal:
            continue

        normalized.append(_normalize_fallback_article(parsed, journal_name, 'Europe PMC fallback'))

    print(f"Extracted {len(normalized)} articles from Europe PMC for {journal_name}")
    return normalized


def fetch_journal_list_with_fallback(
    journal_key: str,
    headless: bool = True,
    timeout: int = 30,
    days: Optional[int] = None
) -> Tuple[List[Dict], str]:
    """Fetch a Cell Press journal list, falling back to PubMed then Europe PMC."""
    articles, journal_name = fetch_journal_list(
        journal_key=journal_key,
        headless=headless,
        timeout=timeout
    )

    if articles:
        return articles, journal_name

    print(f"Web scraping returned no articles for {journal_name}; trying PubMed fallback...")
    articles = _fetch_journal_from_pubmed(journal_key, days=days)
    if articles:
        return articles, journal_name

    print(f"PubMed returned no articles for {journal_name}; trying Europe PMC/PMC fallback...")
    articles = _fetch_journal_from_europepmc(journal_key, days=days)
    return articles, journal_name


def fetch_journal_list(journal_key: str, headless: bool = True, timeout: int = 30) -> Tuple[List[Dict], str]:
    """
    Fetch article list from a Cell Press journal.

    Args:
        journal_key: Key from CELL_JOURNALS
        headless: Use headless browser
        timeout: Page load timeout (kept for API compatibility, not used by Scrapling)

    Returns:
        Tuple of (articles list, journal name)
    """
    if journal_key not in CELL_JOURNALS:
        raise ValueError(f"Unknown journal: {journal_key}. Available: {list(CELL_JOURNALS.keys())}")

    config = CELL_JOURNALS[journal_key]
    url = config['url']
    selector = config['selector']
    journal_name = config['name']

    print(f"=" * 80)
    print(f"Cell Press Crawler (Scrapling Beta) - {journal_name}")
    print(f"=" * 80)
    print(f"Fetching: {url}")

    articles = []

    try:
        # Fetch page with Scrapling
        html = _fetch_with_scrapling(url, headless=headless)

        if not html:
            print("[ERROR] Failed to fetch page with Scrapling")
            return [], journal_name

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
            articles, journal_name = fetch_journal_list_with_fallback(
                journal_key,
                headless=headless,
                days=days
            )
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

    parser = argparse.ArgumentParser(description='Cell Press journal crawler (Scrapling Beta)')
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
    parser.add_argument('--no-headless', action='store_true',
                        help='Run browser in visible mode (default: headless)')

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
        delay=args.delay,
        headless=not args.no_headless
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
