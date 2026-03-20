"""
Generic PubMed Crawler

Uses NCBI E-utilities API to search and fetch articles from PubMed.
Can query any journal or perform general searches.

API Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
Rate Limit: Max 3 requests per second without API key
"""

import requests
import datetime
import time
from typing import List, Dict, Optional, Tuple
import jsonlines

# NCBI E-utilities base URL
NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Default delay between requests (to respect rate limit)
DEFAULT_DELAY = 0.4  # seconds (slightly more than 1/3 second)


def search_pubmed(
    query: str,
    max_results: int = 100,
    sort: str = "date",
    delay: float = DEFAULT_DELAY
) -> Tuple[List[str], int]:
    """
    Search PubMed and return PMIDs.
    
    Args:
        query: PubMed search query (e.g., 'J Neurosci[journal] AND 2026/03/18[PDAT]')
        max_results: Maximum number of results to return
        sort: Sort order ('date' for most recent first)
        delay: Delay between API requests
        
    Returns:
        Tuple of (list of PMIDs, total count)
    """
    url = f"{NCBI_BASE_URL}/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': query,
        'retmode': 'json',
        'retmax': max_results,
        'sort': sort
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        idlist = data.get('esearchresult', {}).get('idlist', [])
        total_count = int(data.get('esearchresult', {}).get('count', 0))
        
        time.sleep(delay)
        return idlist, total_count
        
    except requests.RequestException as e:
        print(f"[ERROR] PubMed search failed: {e}")
        return [], 0


def fetch_article_summaries(
    pmids: List[str],
    delay: float = DEFAULT_DELAY
) -> List[Dict]:
    """
    Fetch article summaries (title, authors, date, etc.) for given PMIDs.
    
    Args:
        pmids: List of PubMed IDs
        delay: Delay between API requests
        
    Returns:
        List of article dictionaries
    """
    if not pmids:
        return []
    
    url = f"{NCBI_BASE_URL}/esummary.fcgi"
    params = {
        'db': 'pubmed',
        'id': ','.join(pmids),
        'retmode': 'json'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = []
        result_data = data.get('result', {})
        
        for pmid in pmids:
            article = result_data.get(pmid, {})
            if article:
                parsed = parse_pubmed_article(article)
                if parsed:
                    results.append(parsed)
        
        time.sleep(delay)
        return results
        
    except requests.RequestException as e:
        print(f"[ERROR] PubMed summary fetch failed: {e}")
        return []


def fetch_article_abstracts(
    pmids: List[str],
    delay: float = DEFAULT_DELAY
) -> Dict[str, str]:
    """
    Fetch abstracts for given PMIDs.
    
    Args:
        pmids: List of PubMed IDs
        delay: Delay between API requests
        
    Returns:
        Dictionary mapping PMID to abstract text
    """
    if not pmids:
        return {}
    
    url = f"{NCBI_BASE_URL}/efetch.fcgi"
    params = {
        'db': 'pubmed',
        'id': ','.join(pmids),
        'retmode': 'xml',
        'rettype': 'abstract'
    }
    
    try:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        
        # Parse XML to extract abstracts
        from xml.etree import ElementTree as ET
        root = ET.fromstring(response.content)
        
        abstracts = {}
        for article in root.findall('.//PubmedArticle'):
            pmid_elem = article.find('.//PMID')
            if pmid_elem is None:
                continue
            pmid = pmid_elem.text
            
            abstract_elem = article.find('.//Abstract/AbstractText')
            if abstract_elem is not None and abstract_elem.text:
                abstracts[pmid] = abstract_elem.text
            else:
                # Try to get other abstract fields
                abstract_parts = article.findall('.//Abstract/AbstractText')
                parts = []
                for part in abstract_parts:
                    label = part.get('Label', '')
                    text = part.text or ''
                    if label:
                        parts.append(f"{label}: {text}")
                    else:
                        parts.append(text)
                if parts:
                    abstracts[pmid] = ' '.join(parts)
        
        time.sleep(delay)
        return abstracts
        
    except Exception as e:
        print(f"[ERROR] PubMed abstract fetch failed: {e}")
        return {}


def parse_pubmed_article(article: Dict) -> Optional[Dict]:
    """
    Parse a PubMed article summary into our standard format.
    
    Args:
        article: Raw article data from PubMed summary API
        
    Returns:
        Parsed paper dictionary or None
    """
    try:
        pmid = article.get('uid', '')
        title = article.get('title', '').strip()
        
        if not title:
            return None
        
        # Extract authors
        authors = []
        author_list = article.get('authors', [])
        for author in author_list:
            name = author.get('name', '')
            if name:
                authors.append(name)
        
        # Extract date - prefer epub date, then pub date
        epub_date = article.get('epubdate', '')
        pub_date = article.get('pubdate', '')
        sort_date = article.get('sortpubdate', '')
        
        # Use the most specific date available
        date_str = epub_date or pub_date or sort_date
        date_formatted = parse_pubmed_date(date_str)
        
        # Extract DOI
        article_ids = article.get('articleids', [])
        doi = ''
        for aid in article_ids:
            if aid.get('idtype') == 'doi':
                doi = aid.get('value', '')
                break
        
        # Extract journal info
        journal = article.get('fulljournalname', '') or article.get('source', '')
        volume = article.get('volume', '')
        issue = article.get('issue', '')
        pages = article.get('pages', '')
        
        # Determine article type
        pub_types = article.get('pubtype', [])
        article_type = 'Article'
        
        if isinstance(pub_types, list):
            pub_type_str = ' '.join(pub_types).lower()
            if 'review' in pub_type_str:
                article_type = 'Review Article'
            elif 'editorial' in pub_type_str:
                article_type = 'Editorial'
        
        # Construct URLs
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        doi_url = f"https://doi.org/{doi}" if doi else ''
        
        return {
            'type': article_type,
            'title': title,
            'authors': authors,
            'date': date_formatted,
            'url': pubmed_url,
            'abstract': '',  # Will be filled separately if needed
            'doi': doi,
            'pmid': pmid,
            'journal': journal,
            'journal_volume': volume,
            'journal_issue': issue,
            'page_info': pages,
            'doi_url': doi_url,
            'pubmed_url': pubmed_url,
            'source': journal or 'PubMed'
        }
        
    except Exception as e:
        print(f"[WARN] Failed to parse PubMed article: {e}")
        return None


def parse_pubmed_date(date_str: str) -> str:
    """
    Parse PubMed date format to 'DD MMM YYYY'.
    
    PubMed dates can be:
    - 2026 Mar 18
    - 2026 Mar
    - 2026
    """
    if not date_str:
        return ''
    
    date_str = str(date_str).strip()
    
    # Try different formats
    formats = [
        '%Y %b %d',   # 2026 Mar 18
        '%Y %B %d',   # 2026 March 18
        '%Y %b',      # 2026 Mar
        '%Y %B',      # 2026 March
        '%Y',         # 2026
        '%Y-%m-%d',   # 2026-03-18
    ]
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            return dt.strftime('%d %b %Y')
        except ValueError:
            continue
    
    return date_str


def fetch_articles_by_journal(
    journal_name: str,
    days: int = 7,
    max_results: int = 100,
    fetch_abstracts: bool = False,
    exclude_types: List[str] = None,
    delay: float = DEFAULT_DELAY
) -> List[Dict]:
    """
    Fetch articles from a specific journal.
    
    Args:
        journal_name: Journal name (e.g., 'J Neurosci', 'Journal of Neurophysiology')
        days: Number of days to look back
        max_results: Maximum number of results
        fetch_abstracts: Whether to fetch full abstracts
        exclude_types: Article types to exclude (default: ['Erratum', 'Correction'])
        delay: Delay between API requests
        
    Returns:
        List of paper dictionaries
    """
    if exclude_types is None:
        exclude_types = ['Erratum', 'Correction', 'Retraction']
    
    # Calculate date range
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days)
    
    # Build query
    # PubMed date format: YYYY/MM/DD
    start_str = start_date.strftime('%Y/%m/%d')
    end_str = end_date.strftime('%Y/%m/%d')
    
    query = f'{journal_name}[journal] AND {start_str}:{end_str}[PDAT]'
    
    print(f"Query: {query}")
    print(f"Date range: {start_str} to {end_str}")
    
    # Search for PMIDs
    pmids, total_count = search_pubmed(query, max_results=max_results, delay=delay)
    print(f"Total articles found: {total_count}")
    
    if not pmids:
        return []
    
    # Fetch summaries in batches
    all_papers = []
    batch_size = 100  # PubMed recommends batches of 100 or less
    
    for i in range(0, len(pmids), batch_size):
        batch_pmids = pmids[i:i+batch_size]
        print(f"Fetching batch {i//batch_size + 1}/{(len(pmids)-1)//batch_size + 1} ({len(batch_pmids)} articles)...")
        
        papers = fetch_article_summaries(batch_pmids, delay=delay)
        
        # Filter out excluded types and title keywords
        for paper in papers:
            paper_type = paper.get('type', '')
            paper_title = paper.get('title', '').lower()
            
            # Check if type is excluded
            if paper_type in exclude_types:
                continue
            
            # Check if title contains excluded keywords
            is_excluded = False
            for keyword in exclude_types:
                if keyword.lower() in paper_title:
                    is_excluded = True
                    break
            
            if not is_excluded:
                all_papers.append(paper)
        
        print(f"  -> {len(papers)} fetched, {len(all_papers)} kept after filtering")
    
    # Fetch abstracts if requested
    if fetch_abstracts and all_papers:
        print("\nFetching abstracts...")
        pmids_for_abstracts = [p['pmid'] for p in all_papers if p.get('pmid')]
        
        abstracts = {}
        for i in range(0, len(pmids_for_abstracts), batch_size):
            batch = pmids_for_abstracts[i:i+batch_size]
            batch_abstracts = fetch_article_abstracts(batch, delay=delay)
            abstracts.update(batch_abstracts)
        
        # Add abstracts to papers
        for paper in all_papers:
            pmid = paper.get('pmid')
            if pmid and pmid in abstracts:
                paper['abstract'] = abstracts[pmid]
    
    # Sort by date (newest first)
    def parse_date_for_sort(paper):
        try:
            return datetime.datetime.strptime(paper.get('date', ''), '%d %b %Y')
        except ValueError:
            return datetime.datetime.min
    
    all_papers.sort(key=parse_date_for_sort, reverse=True)
    
    return all_papers


def save_pubmed_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/pubmed_{timestamp}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


# ============== Test Functions ==============

def test_journal_search():
    """Test searching for a specific journal."""
    print("\n" + "=" * 80)
    print("Testing PubMed Journal Search")
    print("=" * 80)
    
    # Test with Journal of Neuroscience
    papers = fetch_articles_by_journal(
        journal_name='J Neurosci',
        days=30,
        max_results=999,
        fetch_abstracts=False
    )
    
    print("\n" + "=" * 80)
    print(f"Found {len(papers)} papers")
    print("=" * 80)
    
    if papers:
        for i, paper in enumerate(papers[:3], 1):
            print(f"\n[{i}] {paper['title'][:70]}...")
            print(f"    Date: {paper['date']}")
            print(f"    Type: {paper['type']}")
            print(f"    Authors: {', '.join(paper['authors'][:2])}{'...' if len(paper['authors']) > 2 else ''}")
            print(f"    PMID: {paper['pmid']}")
        
        save_pubmed_papers(papers, "getfiles/pubmed_test.jsonl")
    
    return papers


def test_general_search():
    """Test a general search query."""
    print("\n" + "=" * 80)
    print("Testing PubMed General Search")
    print("=" * 80)
    
    query = 'neuroscience AND 2026[PDAT]'
    pmids, total = search_pubmed(query, max_results=5)
    
    print(f"Query: {query}")
    print(f"Total found: {total}")
    print(f"PMIDs: {pmids}")
    
    if pmids:
        papers = fetch_article_summaries(pmids)
        print("\nArticles:")
        for paper in papers:
            print(f"  - {paper['date']}: {paper['title'][:60]}...")
    
    return pmids


if __name__ == '__main__':
    test_journal_search()
    test_general_search()
