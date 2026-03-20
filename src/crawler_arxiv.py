"""
Crawler for arXiv Neuroscience-related Categories
API Docs: http://export.arxiv.org/api/query

Key categories:
- q-bio.NC: Neurons and Cognition
- q-bio.TO: Tissues and Organs
- q-bio.MN: Molecular Networks
"""
import requests
import datetime
import time
from xml.etree import ElementTree as ET
from typing import List, Dict, Optional
import jsonlines

# arXiv API base URL
ARXIV_API_URL = "http://export.arxiv.org/api/query"

# Core neuroscience categories
NEUROSCIENCE_CATEGORIES = [
    "q-bio.NC",  # Neurons and Cognition - Primary category for neuroscience
    "q-bio.TO",  # Tissues and Organs - Includes neural tissues
    "q-bio.MN",  # Molecular Networks - Molecular neuroscience
    "q-bio.BM",  # Biomolecules
    "q-bio.QM",  # Quantitative Methods (neuroimaging analysis)
]

# Keep for backward compatibility
NEUROSCIENCE_CATEGORY = "q-bio.NC"

# Extended categories for broader search (optional)
EXTENDED_CATEGORIES = [
    "q-bio.NC",  # Neurons and Cognition
    "q-bio.TO",  # Tissues and Organs
    "q-bio.MN",  # Molecular Networks
    "q-bio.BM",  # Biomolecules
    "cs.AI",     # Artificial Intelligence (neuroscience-related ML)
    "cs.CV",     # Computer Vision (brain imaging)
    "cs.LG",     # Machine Learning (computational neuroscience)
    "q-bio.QM",  # Quantitative Methods (neuroimaging analysis)
]


def fetch_arxiv_papers(
    category: str = NEUROSCIENCE_CATEGORY,
    max_results: int = 50,
    start: int = 0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = "submittedDate",
    sort_order: str = "descending"
) -> List[Dict]:
    """
    Fetch papers from arXiv API.
    
    Args:
        category: arXiv category code
        max_results: Maximum number of results to return
        start: Starting index for pagination
        date_from: Start date in YYYY-MM-DD format (optional)
        date_to: End date in YYYY-MM-DD format (optional)
        sort_by: Sort field ('relevance', 'lastUpdatedDate', 'submittedDate')
        sort_order: 'ascending' or 'descending'
    
    Returns:
        List of paper dictionaries
    """
    # Build search query
    query = f"cat:{category}"
    
    # Add date range if specified
    if date_from and date_to:
        query += f"+AND+submittedDate:[{date_from}+TO+{date_to}]"
    elif date_from:
        query += f"+AND+submittedDate:[{date_from}+TO+2099-12-31]"
    elif date_to:
        query += f"+AND+submittedDate:[2000-01-01+TO+{date_to}]"
    
    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order
    }
    
    try:
        response = requests.get(ARXIV_API_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Failed to fetch from arXiv: {e}")
        return []
    
    # Parse Atom XML response
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        print(f"[ERROR] Failed to parse XML: {e}")
        return []
    
    # Define namespaces
    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'arxiv': 'http://arxiv.org/schemas/atom'
    }
    
    papers = []
    
    # Extract entries
    for entry in root.findall('atom:entry', ns):
        paper = parse_arxiv_entry(entry, ns)
        if paper:
            papers.append(paper)
    
    return papers


def parse_arxiv_entry(entry: ET.Element, ns: Dict[str, str]) -> Optional[Dict]:
    """Parse a single arXiv entry (Atom entry element)."""
    try:
        # Extract ID (arXiv ID)
        id_elem = entry.find('atom:id', ns)
        arxiv_id = id_elem.text if id_elem is not None else ""
        # Extract just the arXiv ID from the URL
        if '/abs/' in arxiv_id:
            arxiv_id = arxiv_id.split('/abs/')[-1]
        
        # Extract title
        title_elem = entry.find('atom:title', ns)
        title = title_elem.text.strip() if title_elem is not None else "No title"
        # Clean up whitespace in title
        title = ' '.join(title.split())
        
        # Extract authors
        authors = []
        for author_elem in entry.findall('atom:author', ns):
            name_elem = author_elem.find('atom:name', ns)
            if name_elem is not None:
                authors.append(name_elem.text.strip())
        
        # Extract published date
        published_elem = entry.find('atom:published', ns)
        published = published_elem.text[:10] if published_elem is not None else ""
        # Format: YYYY-MM-DD -> DD MMM YYYY
        try:
            dt = datetime.datetime.strptime(published, "%Y-%m-%d")
            published_formatted = dt.strftime("%d %b %Y")
        except ValueError:
            published_formatted = published
        
        # Extract updated date
        updated_elem = entry.find('atom:updated', ns)
        updated = updated_elem.text[:10] if updated_elem is not None else published
        
        # Extract summary (abstract)
        summary_elem = entry.find('atom:summary', ns)
        abstract = summary_elem.text.strip() if summary_elem is not None else ""
        # Clean up whitespace
        abstract = ' '.join(abstract.split())
        
        # Extract categories
        categories = []
        for category_elem in entry.findall('atom:category', ns):
            term = category_elem.get('term')
            if term:
                categories.append(term)
        
        # Extract primary category
        primary_category_elem = entry.find('arxiv:primary_category', ns)
        primary_category = primary_category_elem.get('term') if primary_category_elem is not None else ""
        
        # Extract links
        pdf_url = ""
        html_url = ""
        for link_elem in entry.findall('atom:link', ns):
            link_type = link_elem.get('type', '')
            link_title = link_elem.get('title', '')
            href = link_elem.get('href', '')
            
            if link_type == 'application/pdf' or link_title == 'pdf':
                pdf_url = href
            elif link_elem.get('rel') == 'alternate':
                html_url = href
        
        # Construct URLs if not provided
        if not html_url and arxiv_id:
            html_url = f"https://arxiv.org/abs/{arxiv_id}"
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        
        # Extract comment (if available)
        comment_elem = entry.find('arxiv:comment', ns)
        comment = comment_elem.text.strip() if comment_elem is not None else ""
        
        # Extract journal reference (if available)
        journal_elem = entry.find('arxiv:journal_ref', ns)
        journal_ref = journal_elem.text.strip() if journal_elem is not None else ""
        
        # Extract DOI (if available)
        doi_elem = entry.find('arxiv:doi', ns)
        doi = doi_elem.text.strip() if doi_elem is not None else ""
        
        return {
            'type': 'Article',
            'title': title,
            'authors': authors,
            'date': published_formatted,
            'url': html_url,
            'abstract': abstract,
            'arxiv_id': arxiv_id,
            'arxiv_categories': categories,
            'arxiv_primary_category': primary_category,
            'pdf_url': pdf_url,
            'updated': updated,
            'comment': comment,
            'journal_ref': journal_ref,
            'doi': doi,
            'source': 'arXiv'
        }
    
    except Exception as e:
        print(f"[WARN] Failed to parse arXiv entry: {e}")
        return None


def fetch_recent_arxiv_papers(
    days: int = 7,
    categories: Optional[List[str]] = None,
    max_results_per_category: int = 50,
    fallback_if_empty: bool = True,
    use_extended: bool = False
) -> List[Dict]:
    """
    Fetch recent papers from arXiv within the specified number of days.
    
    Note: Uses local date filtering because arXiv API's date filter is unreliable.
    
    Args:
        days: Number of days to look back
        categories: List of arXiv categories to search (default: NEUROSCIENCE_CATEGORIES)
        max_results_per_category: Maximum results per category
        fallback_if_empty: If True and no papers found with date filter, 
                          fetch recent papers without date filter
        use_extended: If True, use EXTENDED_CATEGORIES instead of NEUROSCIENCE_CATEGORIES
    
    Returns:
        List of paper dictionaries
    """
    if categories is None:
        categories = EXTENDED_CATEGORIES if use_extended else NEUROSCIENCE_CATEGORIES
    
    # Calculate cutoff date for local filtering
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    
    all_papers = []
    
    for category in categories:
        print(f"Fetching arXiv papers for category: {category}")
        
        # Fetch recent papers without API date filter (it's unreliable)
        # Fetch more than needed to ensure we get enough after filtering
        fetch_count = max(max_results_per_category * 2, 100)
        papers = fetch_arxiv_papers(
            category=category,
            max_results=fetch_count,
            sort_by="submittedDate",
            sort_order="descending"
        )
        
        # Filter locally by date
        filtered_papers = []
        for paper in papers:
            try:
                # Parse paper date (format: "12 Mar 2026")
                paper_date = datetime.datetime.strptime(paper['date'], "%d %b %Y")
                if paper_date >= cutoff_date:
                    filtered_papers.append(paper)
            except (ValueError, KeyError):
                # If date parsing fails, include the paper to be safe
                filtered_papers.append(paper)
        
        # Apply limit after filtering
        filtered_papers = filtered_papers[:max_results_per_category]
        
        # Fallback: if no papers found and fallback enabled, use unfiltered results
        if not filtered_papers and fallback_if_empty and papers:
            print(f"  No papers in date range, using {len(papers[:max_results_per_category])} most recent papers")
            filtered_papers = papers[:max_results_per_category]
        
        all_papers.extend(filtered_papers)
        print(f"  Found {len(filtered_papers)} papers in last {days} days")
        
        # Be nice to the API
        time.sleep(1)
    
    # Remove duplicates based on arXiv ID
    seen_ids = set()
    unique_papers = []
    for paper in all_papers:
        if paper['arxiv_id'] not in seen_ids:
            seen_ids.add(paper['arxiv_id'])
            unique_papers.append(paper)
    
    # Sort by date (newest first)
    unique_papers.sort(key=lambda x: x['date'], reverse=True)
    
    return unique_papers


def save_arxiv_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        filepath = f"getfiles/arxiv-{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    return filepath


if __name__ == '__main__':
    # Example: Fetch last 7 days of neuroscience papers
    print("Fetching recent arXiv papers...")
    papers = fetch_recent_arxiv_papers(days=7, max_results_per_category=20)
    print(f"\nTotal papers fetched: {len(papers)}")
    
    if papers:
        filepath = save_arxiv_papers(papers)
        print(f"Saved to: {filepath}")
        
        # Print first paper as example
        print("\n--- Example Paper ---")
        paper = papers[0]
        print(f"Title: {paper['title'][:100]}...")
        print(f"Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
        print(f"Date: {paper['date']}")
        print(f"Abstract: {paper['abstract'][:200]}...")
        print(f"URL: {paper['url']}")
