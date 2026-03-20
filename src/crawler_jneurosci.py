"""
Crawler for Journal of Neuroscience

Uses PubMed API to search for recent articles from Journal of Neuroscience.
PubMed updates faster than Europe PMC for recent articles.

Note: Journal Club articles are marked on the journal website but not in PubMed.
We maintain a list of known Journal Club PMIDs to filter them.
"""

import datetime
from typing import List, Dict, Optional
import jsonlines

# Import from generic PubMed crawler
from crawler_pubmed import fetch_articles_by_journal, save_pubmed_papers

# Journal name in PubMed (MEDLINE abbreviation)
JOURNAL_NAME = "J Neurosci"

# Default: look back 7 days
DEFAULT_DAYS_BACK = 7

# Journal Club filtering criteria
# Journal Club articles are typically in specific volumes/issues and lack abstracts
JOURNAL_CLUB_VOLUME = '46'
JOURNAL_CLUB_ISSUE = '11'


def is_journal_club_article(paper: Dict) -> bool:
    """
    Check if an article is a Journal Club article.
    
    Journal Club articles are typically:
    - In specific volume/issue (e.g., Vol 46, Issue 11)
    - Lack abstracts (they are commentaries, not research articles)
    
    Args:
        paper: Article dictionary
        
    Returns:
        True if it's a Journal Club article
    """
    volume = paper.get('journal_volume', '')
    issue = paper.get('journal_issue', '')
    abstract = paper.get('abstract', '').strip()
    
    # Check if it's in the target volume/issue and lacks abstract
    if volume == JOURNAL_CLUB_VOLUME and issue == JOURNAL_CLUB_ISSUE:
        if not abstract:
            return True
    
    return False


def fetch_jneurosci_papers(days: int = DEFAULT_DAYS_BACK,
                           max_results: int = 100,
                           fetch_abstracts: bool = False,
                           delay: float = 0.4,
                           include_journal_club: bool = False) -> List[Dict]:
    """
    Fetch papers from Journal of Neuroscience using PubMed API.
    
    Args:
        days: Number of days to look back
        max_results: Maximum number of results to fetch
        fetch_abstracts: Whether to fetch full abstracts (slower)
        delay: Delay between API requests in seconds
        include_journal_club: Whether to include Journal Club articles
        
    Returns:
        List of paper dictionaries
    """
    print("=" * 80)
    print(f"Fetching from Journal of Neuroscience via PubMed (last {days} days)...")
    if not include_journal_club:
        print(f"(Filtering out Journal Club articles from Vol {JOURNAL_CLUB_VOLUME}, Issue {JOURNAL_CLUB_ISSUE})")
    print("=" * 80)
    
    papers = fetch_articles_by_journal(
        journal_name=JOURNAL_NAME,
        days=days,
        max_results=max_results,
        fetch_abstracts=fetch_abstracts,
        exclude_types=['Erratum', 'Correction', 'Retraction'],
        delay=delay
    )
    
    # Filter out Journal Club articles unless explicitly included
    filtered_papers = []
    journal_club_count = 0
    
    for paper in papers:
        if is_journal_club_article(paper):
            journal_club_count += 1
            if include_journal_club:
                paper['type'] = 'Journal Club'
                paper['source'] = 'Journal of Neuroscience (Journal Club)'
                filtered_papers.append(paper)
            continue
        
        # Update source field for regular articles
        paper['source'] = 'Journal of Neuroscience'
        filtered_papers.append(paper)
    
    if journal_club_count > 0:
        if include_journal_club:
            print(f"\nIncluded {journal_club_count} Journal Club article(s)")
        else:
            print(f"\nFiltered out {journal_club_count} Journal Club article(s)")
    
    print(f"\nTotal Journal of Neuroscience papers collected: {len(filtered_papers)}")
    return filtered_papers


def save_jneurosci_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/jneurosci_{timestamp}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


# ============== Test Functions ==============

def test_fetch():
    """Test fetching papers from Journal of Neuroscience."""
    print("\n" + "=" * 80)
    print("Testing Journal of Neuroscience Crawler (via PubMed)")
    print("=" * 80)
    
    # Test with last 30 days
    papers = fetch_jneurosci_papers(days=7, max_results=999, fetch_abstracts=True)
    
    if papers:
        print("\n" + "=" * 80)
        print("Sample Papers:")
        print("=" * 80)
        for i, paper in enumerate(papers[:3], 1):
            print(f"\n[{i}] {paper['title']}")
            print(f"    Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
            print(f"    Date: {paper['date']}")
            print(f"    Type: {paper['type']}")
            print(f"    DOI: {paper.get('doi', 'N/A')}")
            print(f"    PMID: {paper.get('pmid', 'N/A')}")
        
        # Show article type breakdown
        print("\n" + "=" * 80)
        print("Article Type Breakdown:")
        print("=" * 80)
        type_counts = {}
        for p in papers:
            t = p['type']
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, count in sorted(type_counts.items()):
            print(f"  {t}: {count}")
        
        # Save results
        save_jneurosci_papers(papers, "getfiles/jneurosci_test.jsonl")
    else:
        print("\nNo papers found.")
    
    return papers


if __name__ == '__main__':
    test_fetch()
