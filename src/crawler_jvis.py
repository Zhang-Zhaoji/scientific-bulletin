"""
Crawler for Journal of Vision

Uses PubMed API to search for recent articles.
"""

import datetime
from typing import List, Dict, Optional
import jsonlines

from crawler_pubmed import fetch_articles_by_journal

# Journal name in PubMed (MEDLINE abbreviation)
JOURNAL_NAME = "J Vis"

# Default: look back 7 days
DEFAULT_DAYS_BACK = 7


def fetch_jvis_papers(days: int = DEFAULT_DAYS_BACK,
                      max_results: int = 100,
                      fetch_abstracts: bool = False,
                      delay: float = 0.4) -> List[Dict]:
    """
    Fetch papers from Journal of Vision using PubMed API.
    
    Args:
        days: Number of days to look back
        max_results: Maximum number of results to fetch
        fetch_abstracts: Whether to fetch full abstracts (slower)
        delay: Delay between API requests in seconds
        
    Returns:
        List of paper dictionaries
    """
    print("=" * 80)
    print(f"Fetching from Journal of Vision via PubMed (last {days} days)...")
    print("=" * 80)
    
    papers = fetch_articles_by_journal(
        journal_name=JOURNAL_NAME,
        days=days,
        max_results=max_results,
        fetch_abstracts=fetch_abstracts,
        exclude_types=['Erratum', 'Correction', 'Retraction'],
        delay=delay
    )
    
    # Update source field
    for paper in papers:
        paper['source'] = 'Journal of Vision'
    
    print(f"\nTotal Journal of Vision papers collected: {len(papers)}")
    return papers


def save_jvis_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/jvis_{timestamp}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("Testing Journal of Vision Crawler")
    print("=" * 80)
    
    papers = fetch_jvis_papers(days=7, max_results=999, fetch_abstracts=True)
    
    if papers:
        print("\nSample Papers:")
        for i, paper in enumerate(papers[:3], 1):
            print(f"\n[{i}] {paper['title'][:70]}...")
            print(f"    Date: {paper['date']}")
            print(f"    Authors: {', '.join(paper['authors'][:2])}{'...' if len(paper['authors']) > 2 else ''}")
        
        save_jvis_papers(papers, "getfiles/jvis_test.jsonl")
    else:
        print("\nNo papers found.")
