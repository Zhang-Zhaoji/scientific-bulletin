"""
Test script for arXiv and bioRxiv crawlers
Usage: python src/test_crawlers.py [--arxiv] [--biorxiv] [--days N] [--limit N]
"""
import argparse
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler_arxiv import (
    fetch_recent_arxiv_papers, 
    fetch_arxiv_papers,
    save_arxiv_papers,
    NEUROSCIENCE_CATEGORY,
    RELEVANT_CATEGORIES
)
from crawler_biorxiv import (
    fetch_recent_biorxiv_papers,
    fetch_biorxiv_papers_by_date,
    save_biorxiv_papers
)


def test_arxiv(days: int = 3, limit: int = 10):
    """Test arXiv crawler."""
    print("=" * 80)
    print("TESTING ARXIV CRAWLER")
    print("=" * 80)
    
    print(f"\n[1] Fetching recent {limit} papers from last {days} days...")
    print(f"    Category: {NEUROSCIENCE_CATEGORY} (Neurons and Cognition)")
    
    papers = fetch_recent_arxiv_papers(
        days=days,
        categories=[NEUROSCIENCE_CATEGORY],
        max_results_per_category=limit
    )
    
    print(f"\n[2] Results: {len(papers)} papers fetched")
    
    if not papers:
        print("    No papers found. This could be due to:")
        print("    - Network connectivity issues")
        print("    - arXiv API being temporarily unavailable")
        print("    - No papers in the specified date range")
        return []
    
    # Display first 3 papers
    print(f"\n[3] Showing first {min(3, len(papers))} papers:")
    for i, paper in enumerate(papers[:3], 1):
        print(f"\n    --- Paper {i} ---")
        print(f"    Title: {paper['title'][:80]}{'...' if len(paper['title']) > 80 else ''}")
        print(f"    Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
        print(f"    Date: {paper['date']}")
        print(f"    arXiv ID: {paper['arxiv_id']}")
        print(f"    Categories: {', '.join(paper['arxiv_categories'][:2])}")
        print(f"    URL: {paper['url']}")
        print(f"    PDF: {paper['pdf_url']}")
        abstract_preview = paper['abstract'][:150] if paper['abstract'] else "No abstract"
        print(f"    Abstract: {abstract_preview}{'...' if len(paper.get('abstract', '')) > 150 else ''}")
    
    # Test saving
    print(f"\n[4] Testing save functionality...")
    try:
        filepath = save_arxiv_papers(papers)
        print(f"    Saved to: {filepath}")
        print(f"    File exists: {os.path.exists(filepath)}")
        print(f"    File size: {os.path.getsize(filepath)} bytes")
    except Exception as e:
        print(f"    [ERROR] Failed to save: {e}")
    
    return papers


def test_biorxiv(days: int = 3, limit: int = 10):
    """Test bioRxiv crawler."""
    print("\n" + "=" * 80)
    print("TESTING BIORXIV CRAWLER")
    print("=" * 80)
    
    print(f"\n[1] Fetching recent papers from last {days} days...")
    print(f"    Filter: Neuroscience-related papers (all categories)")
    
    papers = fetch_recent_biorxiv_papers(
        days=days,
        categories=None,  # Fetch all, but we could filter by ['neuroscience'] if needed
        max_results=limit
    )
    
    print(f"\n[2] Results: {len(papers)} papers fetched")
    
    if not papers:
        print("    No papers found. This could be due to:")
        print("    - Network connectivity issues")
        print("    - bioRxiv API being temporarily unavailable")
        print("    - No papers in the specified date range")
        return []
    
    # Display first 3 papers
    print(f"\n[3] Showing first {min(3, len(papers))} papers:")
    for i, paper in enumerate(papers[:3], 1):
        print(f"\n    --- Paper {i} ---")
        print(f"    Title: {paper['title'][:80]}{'...' if len(paper['title']) > 80 else ''}")
        print(f"    Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper['authors']) > 3 else ''}")
        print(f"    Date: {paper['date']}")
        print(f"    DOI: {paper['doi']}")
        print(f"    Category: {paper['biorxiv_category']}")
        print(f"    URL: {paper['url']}")
        print(f"    PDF: {paper['pdf_url']}")
        abstract_preview = paper['abstract'][:150] if paper['abstract'] else "No abstract"
        print(f"    Abstract: {abstract_preview}{'...' if len(paper.get('abstract', '')) > 150 else ''}")
    
    # Test saving
    print(f"\n[4] Testing save functionality...")
    try:
        filepath = save_biorxiv_papers(papers)
        print(f"    Saved to: {filepath}")
        print(f"    File exists: {os.path.exists(filepath)}")
        print(f"    File size: {os.path.getsize(filepath)} bytes")
    except Exception as e:
        print(f"    [ERROR] Failed to save: {e}")
    
    return papers


def test_comparison(arxiv_papers, biorxiv_papers):
    """Compare results from both sources."""
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    
    print(f"\n[1] arXiv Papers: {len(arxiv_papers)}")
    print(f"[2] bioRxiv Papers: {len(biorxiv_papers)}")
    print(f"[3] Total Papers: {len(arxiv_papers) + len(biorxiv_papers)}")
    
    if arxiv_papers:
        arxiv_dates = [p['date'] for p in arxiv_papers]
        print(f"\n[4] arXiv Date Range: {min(arxiv_dates)} to {max(arxiv_dates)}")
    
    if biorxiv_papers:
        biorxiv_dates = [p['date'] for p in biorxiv_papers]
        print(f"[5] bioRxiv Date Range: {min(biorxiv_dates)} to {max(biorxiv_dates)}")
    
    # Check for potential overlaps (same title or similar authors)
    if arxiv_papers and biorxiv_papers:
        print("\n[6] Checking for potential overlaps...")
        arxiv_titles = {p['title'].lower().strip(): p for p in arxiv_papers}
        overlaps = 0
        for biorxiv_paper in biorxiv_papers:
            biorxiv_title = biorxiv_paper['title'].lower().strip()
            if biorxiv_title in arxiv_titles:
                overlaps += 1
                print(f"    Potential overlap found: {biorxiv_paper['title'][:60]}...")
        
        if overlaps == 0:
            print("    No obvious overlaps detected (based on title matching)")
        else:
            print(f"    Found {overlaps} potential overlapping papers")


def main():
    parser = argparse.ArgumentParser(
        description='Test arXiv and bioRxiv crawlers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/test_crawlers.py              # Test both crawlers
  python src/test_crawlers.py --arxiv      # Test only arXiv
  python src/test_crawlers.py --biorxiv    # Test only bioRxiv
  python src/test_crawlers.py --days 7 --limit 20  # Last 7 days, 20 papers each
        """
    )
    
    parser.add_argument('--arxiv', action='store_true',
                        help='Test only arXiv crawler')
    parser.add_argument('--biorxiv', action='store_true',
                        help='Test only bioRxiv crawler')
    parser.add_argument('--days', type=int, default=3,
                        help='Number of days to look back (default: 3)')
    parser.add_argument('--limit', type=int, default=10,
                        help='Maximum papers to fetch per source (default: 10)')
    
    args = parser.parse_args()
    
    # If neither flag is set, test both
    test_both = not args.arxiv and not args.biorxiv
    
    arxiv_papers = []
    biorxiv_papers = []
    
    try:
        if test_both or args.arxiv:
            arxiv_papers = test_arxiv(days=args.days, limit=args.limit)
        
        if test_both or args.biorxiv:
            biorxiv_papers = test_biorxiv(days=args.days, limit=args.limit)
        
        if test_both or (args.arxiv and args.biorxiv):
            test_comparison(arxiv_papers, biorxiv_papers)
        
        print("\n" + "=" * 80)
        print("TEST COMPLETED")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
