"""
Crawler for PLOS (Public Library of Science) journals

Uses PubMed API to search for recent articles from PLOS journals.
PLOS publishes open-access research across multiple disciplines including neuroscience.

PubMed Journal Names (MEDLINE abbreviation):
  - PLoS Biology: PLoS Biol
  - PLoS Computational Biology: PLoS Comput Biol
  - PLoS One: PLoS One
"""

import datetime
from typing import List, Dict, Optional
import jsonlines

# Import from generic PubMed crawler
from crawler_pubmed import fetch_articles_by_journal

# PLOS journals with PubMed MEDLINE abbreviations
PLOS_JOURNALS = {
    'PLoS Biology': 'PLoS Biol',
    'PLoS Computational Biology': 'PLoS Comput Biol',
    'PLoS One': 'PLoS One',
}

# Default: look back 7 days
DEFAULT_DAYS_BACK = 7


def fetch_plos_papers(days: int = DEFAULT_DAYS_BACK,
                      max_results: int = 100,
                      fetch_abstracts: bool = False,
                      delay: float = 0.4) -> List[Dict]:
    """
    Fetch papers from PLOS journals using PubMed API.

    Iterates over all PLOS journals. For PLoS One, uses a smaller max_results
    because it publishes a very high volume of articles and fetch_articles_by_journal
    does not support a custom neuroscience-filtered query.

    Args:
        days: Number of days to look back
        max_results: Maximum number of results to fetch per journal
        fetch_abstracts: Whether to fetch full abstracts (slower)
        delay: Delay between API requests in seconds

    Returns:
        List of paper dictionaries
    """
    all_papers = []

    for journal_display, journal_name in PLOS_JOURNALS.items():
        print("=" * 80)
        print(f"Fetching from {journal_display} via PubMed (last {days} days)...")
        print("=" * 80)

        # PLoS One publishes a huge volume; fetch_articles_by_journal does not
        # support a custom neuroscience-filtered query, so use a smaller cap.
        journal_max_results = 50 if journal_name == 'PLoS One' else max_results

        papers = fetch_articles_by_journal(
            journal_name=journal_name,
            days=days,
            max_results=journal_max_results,
            fetch_abstracts=fetch_abstracts,
            exclude_types=['Erratum', 'Correction', 'Retraction'],
            delay=delay
        )

        # Update source and journal fields for all papers
        for paper in papers:
            paper['source'] = 'PLOS'
            paper['journal'] = journal_display

        print(f"  -> {len(papers)} papers from {journal_display}")
        all_papers.extend(papers)

    print(f"\nTotal PLOS papers collected: {len(all_papers)}")
    return all_papers


def save_plos_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/plos_{timestamp}.jsonl"

    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)

    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


# ============== Test Functions ==============

def test_fetch():
    """Test fetching papers from PLOS journals."""
    print("\n" + "=" * 80)
    print("Testing PLOS Crawler (via PubMed)")
    print("=" * 80)

    # Test with last 7 days
    papers = fetch_plos_papers(days=7, max_results=100, fetch_abstracts=True)

    if papers:
        print("\n" + "=" * 80)
        print("Sample Papers:")
        print("=" * 80)
        for i, paper in enumerate(papers[:5], 1):
            print(f"\n[{i}] {paper['title']}")
            print(f"    Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
            print(f"    Date: {paper['date']}")
            print(f"    Type: {paper['type']}")
            print(f"    Journal: {paper.get('journal', 'N/A')}")
            print(f"    DOI: {paper.get('doi', 'N/A')}")
            print(f"    PMID: {paper.get('pmid', 'N/A')}")

        # Show journal breakdown
        print("\n" + "=" * 80)
        print("Journal Breakdown:")
        print("=" * 80)
        journal_counts = {}
        for p in papers:
            j = p.get('journal', 'Unknown')
            journal_counts[j] = journal_counts.get(j, 0) + 1
        for j, count in sorted(journal_counts.items()):
            print(f"  {j}: {count}")

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
        save_plos_papers(papers, "getfiles/plos_test.jsonl")
    else:
        print("\nNo papers found.")

    return papers


if __name__ == '__main__':
    test_fetch()
