"""
Crawler for eLife

Uses PubMed API to search for recent articles from eLife.
eLife is an open access journal in life sciences and biomedicine,
known for transparent peer review and strong computational neuroscience content.

PubMed Journal Name: Elife
"""

import datetime
from typing import List, Dict, Optional
import jsonlines

# Import from generic PubMed crawler
from crawler_pubmed import fetch_articles_by_journal, save_pubmed_papers

# Journal name in PubMed (MEDLINE abbreviation)
JOURNAL_NAME = "Elife"

# Default: look back 7 days
DEFAULT_DAYS_BACK = 7


def fetch_elife_papers(days: int = DEFAULT_DAYS_BACK,
                       max_results: int = 100,
                       fetch_abstracts: bool = False,
                       delay: float = 0.4) -> List[Dict]:
    """
    Fetch papers from eLife using PubMed API.
    
    Args:
        days: Number of days to look back
        max_results: Maximum number of results to fetch
        fetch_abstracts: Whether to fetch full abstracts (slower)
        delay: Delay between API requests in seconds
        
    Returns:
        List of paper dictionaries
    """
    print("=" * 80)
    print(f"Fetching from eLife via PubMed (last {days} days)...")
    print("=" * 80)
    
    papers = fetch_articles_by_journal(
        journal_name=JOURNAL_NAME,
        days=days,
        max_results=max_results,
        fetch_abstracts=fetch_abstracts,
        exclude_types=['Erratum', 'Correction', 'Retraction'],
        delay=delay
    )
    
    # Update source field for all papers
    for paper in papers:
        paper['source'] = 'eLife'
    
    print(f"\nTotal eLife papers collected: {len(papers)}")
    return papers


def save_elife_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/elife_{timestamp}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


# ============== Test Functions ==============

def test_fetch():
    """Test fetching papers from eLife."""
    print("\n" + "=" * 80)
    print("Testing eLife Crawler (via PubMed)")
    print("=" * 80)
    
    # Test with last 7 days
    papers = fetch_elife_papers(days=7, max_results=999, fetch_abstracts=True)
    
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
        save_elife_papers(papers, "getfiles/elife_test.jsonl")
    else:
        print("\nNo papers found.")
    
    return papers


if __name__ == '__main__':
    test_fetch()
