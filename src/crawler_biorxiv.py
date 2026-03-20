"""
Crawler for bioRxiv (Neuroscience collection)
API Docs: https://api.biorxiv.org/
"""
import requests
import datetime
import time
from typing import List, Dict, Optional
import jsonlines

# bioRxiv API base URL
BIORXIV_API_URL = "https://api.biorxiv.org"

# bioRxiv collections/categories
NEUROSCIENCE_COLLECTION = "neuroscience"

# Other relevant collections
RELEVANT_COLLECTIONS = [
    "neuroscience",
    "bioinformatics",  # Computational neuroscience
    "genetics",        # Neurogenetics
    "animal-behavior-and-cognition",
    "biochemistry",    # Molecular neuroscience
    "cell-biology",    # Cellular neuroscience
]


def fetch_biorxiv_papers_by_category(
    category: str = "neuroscience",
    cursor: Optional[str] = None,
    limit: int = 100
) -> Dict:
    """
    Fetch papers from bioRxiv by category using the details endpoint with category filter.
    Note: bioRxiv API doesn't have a direct collection endpoint, so we fetch by date
    and filter by category on the client side.
    
    Args:
        category: Category name to filter by
        cursor: Pagination cursor (from previous response)
        limit: Number of results per page (max 100)
    
    Returns:
        API response as dictionary
    """
    # Use date range endpoint and filter by category
    # Fetch last 30 days by default
    date_to = datetime.datetime.now()
    date_from = date_to - datetime.timedelta(days=30)
    
    return fetch_biorxiv_papers_by_date_range(
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        cursor=cursor,
        limit=limit
    )


def fetch_biorxiv_papers_by_date_range(
    date_from: str,
    date_to: str,
    cursor: Optional[str] = None,
    limit: int = 100,
    category: Optional[str] = None
) -> Dict:
    """
    Fetch papers from bioRxiv by date range (server-side date).
    Format: YYYY-MM-DD
    
    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        cursor: Pagination cursor
        limit: Number of results per page (max 100)
        category: Category to filter by (e.g., 'neuroscience')
    
    Note: Category filtering is done via query parameter ?category=xxx
    """
    url = f"{BIORXIV_API_URL}/details/biorxiv/{date_from}/{date_to}"
    
    params = {
        "format": "json",
        "limit": min(limit, 100)
    }
    
    if cursor:
        params["cursor"] = cursor
    
    if category:
        params["category"] = category
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[ERROR] Failed to fetch from bioRxiv: {e}")
        return {"collection": [], "messages": []}


def parse_biorxiv_paper(item: Dict) -> Optional[Dict]:
    """Parse a single bioRxiv paper from API response."""
    try:
        # Extract DOI
        doi = item.get('doi', '')
        
        # Extract title
        title = item.get('title', 'No title').strip()
        
        # Extract authors
        authors_raw = item.get('authors', '')
        authors = [a.strip() for a in authors_raw.split(';') if a.strip()] if authors_raw else []
        
        # Extract date - bioRxiv provides 'date' in YYYY-MM-DD format
        date_str = item.get('date', '')
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            date_formatted = dt.strftime("%d %b %Y")
        except ValueError:
            date_formatted = date_str
        
        # Extract version date (if available)
        version_date = item.get('versionedDate', '')
        
        # Extract category
        category = item.get('category', '')
        
        # Extract abstract
        abstract = item.get('abstract', '').strip()
        
        # Construct URLs
        # bioRxiv DOI format: 10.1101/XXXXXX
        if doi.startswith('10.1101/'):
            biorxiv_id = doi.replace('10.1101/', '')
            html_url = f"https://www.biorxiv.org/content/{doi}"
            pdf_url = f"https://www.biorxiv.org/content/{doi}.full.pdf"
        else:
            html_url = f"https://doi.org/{doi}" if doi else ""
            pdf_url = ""
        
        # Extract author corresponding info (if available)
        author_corresponding = item.get('author_corresponding', '')
        author_corresponding_institution = item.get('author_corresponding_institution', '')
        
        return {
            'type': 'Article',
            'title': title,
            'authors': authors,
            'date': date_formatted,
            'url': html_url,
            'abstract': abstract,
            'doi': doi,
            'biorxiv_category': category,
            'pdf_url': pdf_url,
            'author_corresponding': author_corresponding,
            'author_corresponding_institution': author_corresponding_institution,
            'version_date': version_date,
            'source': 'bioRxiv'
        }
    
    except Exception as e:
        print(f"[WARN] Failed to parse bioRxiv paper: {e}")
        return None


def fetch_recent_biorxiv_papers(
    days: int = 7,
    category: Optional[str] = 'neuroscience',
    max_results: int = 200
) -> List[Dict]:
    """
    Fetch recent papers from bioRxiv within the specified number of days.
    
    Args:
        days: Number of days to look back
        category: Category to filter by (default: 'neuroscience'). 
                  Set to None to fetch all categories.
        max_results: Maximum total results to fetch
    
    Returns:
        List of paper dictionaries
    """
    # Calculate date range
    date_to = datetime.datetime.now()
    date_from = date_to - datetime.timedelta(days=days)
    
    date_from_str = date_from.strftime("%Y-%m-%d")
    date_to_str = date_to.strftime("%Y-%m-%d")
    
    if category:
        print(f"Fetching bioRxiv '{category}' papers from {date_from_str} to {date_to_str}")
    else:
        print(f"Fetching bioRxiv papers from {date_from_str} to {date_to_str}")
    
    cursor = None
    fetched_count = 0
    all_papers = []
    
    while fetched_count < max_results:
        response = fetch_biorxiv_papers_by_date_range(
            date_from=date_from_str,
            date_to=date_to_str,
            cursor=cursor,
            limit=100,
            category=category  # Server-side category filtering
        )
        
        papers_data = response.get('collection', [])
        messages = response.get('messages', [])
        
        # Get next cursor from messages
        next_cursor = None
        if messages:
            next_cursor = messages[0].get('cursor', None)
            count = messages[0].get('count', 0)
            total = messages[0].get('total', 0)
            status = messages[0].get('status', 'unknown')
        else:
            count = 0
            total = 0
            status = 'no_messages'
        
        # Check if we've reached the end
        if status != 'ok' or count == 0:
            break
        
        # Parse papers (no need to filter by category - already done server-side)
        for item in papers_data:
            paper = parse_biorxiv_paper(item)
            if paper:
                all_papers.append(paper)
        
        fetched_count += count
        print(f"  Fetched {fetched_count}/{total} papers")
        
        # Check if there are more pages
        if not next_cursor or next_cursor == cursor:
            break
        
        cursor = next_cursor
        
        # Be nice to the API
        time.sleep(0.5)
    
    # Remove duplicates based on DOI
    seen_dois = set()
    unique_papers = []
    for paper in all_papers:
        if paper['doi'] and paper['doi'] not in seen_dois:
            seen_dois.add(paper['doi'])
            unique_papers.append(paper)
        elif not paper['doi']:
            unique_papers.append(paper)
    
    # Sort by date (newest first)
    unique_papers.sort(
        key=lambda x: datetime.datetime.strptime(x['date'], "%d %b %Y") 
        if x.get('date') else datetime.datetime.min,
        reverse=True
    )
    
    print(f"  Found {len(unique_papers)} unique papers")
    
    return unique_papers


def fetch_biorxiv_papers_by_date(
    date_from: str,
    date_to: str,
    max_results: int = 500,
    category: Optional[str] = None
) -> List[Dict]:
    """
    Fetch papers from bioRxiv by specific date range.
    
    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        max_results: Maximum total results
        category: Category to filter by (e.g., 'neuroscience')
    
    Returns:
        List of paper dictionaries
    """
    if category:
        print(f"Fetching bioRxiv '{category}' papers from {date_from} to {date_to}")
    else:
        print(f"Fetching bioRxiv papers from {date_from} to {date_to}")
    
    cursor = None
    fetched_count = 0
    all_papers = []
    
    while fetched_count < max_results:
        response = fetch_biorxiv_papers_by_date_range(
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=100,
            category=category
        )
        
        papers_data = response.get('collection', [])
        messages = response.get('messages', [])
        
        # Get next cursor from messages
        next_cursor = None
        if messages:
            next_cursor = messages[0].get('cursor', None)
            count = messages[0].get('count', 0)
            total = messages[0].get('total', 0)
            status = messages[0].get('status', 'unknown')
        else:
            count = 0
            total = 0
            status = 'no_messages'
        
        # Check if we've reached the end
        if status != 'ok' or count == 0:
            break
        
        # Parse papers
        for item in papers_data:
            paper = parse_biorxiv_paper(item)
            if paper:
                all_papers.append(paper)
        
        fetched_count += count
        print(f"  Fetched {fetched_count}/{total} papers")
        
        # Check if there are more pages
        if not next_cursor or next_cursor == cursor:
            break
        
        cursor = next_cursor
        
        # Be nice to the API
        time.sleep(0.5)
    
    return all_papers


def save_biorxiv_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        filepath = f"getfiles/biorxiv-{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    return filepath


if __name__ == '__main__':
    # Example 1: Fetch recent neuroscience papers
    print("Fetching recent bioRxiv papers...")
    papers = fetch_recent_biorxiv_papers(
        days=7,
        category='neuroscience',  # Use server-side filtering
        max_results=999
    )
    print(f"\nTotal papers fetched: {len(papers)}")
    
    if papers:
        filepath = save_biorxiv_papers(papers)
        print(f"Saved to: {filepath}")
        
        # Print first paper as example
        print("\n--- Example Paper ---")
        paper = papers[0]
        print(f"Title: {paper['title'][:100]}...")
        print(f"Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
        print(f"Date: {paper['date']}")
        print(f"Category: {paper['biorxiv_category']}")
        print(f"Abstract: {paper['abstract'][:200]}...")
        print(f"URL: {paper['url']}")
