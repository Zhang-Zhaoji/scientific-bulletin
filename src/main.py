"""
Neuroscience Bulletin - Main Entry Point

This script coordinates all journal crawlers to fetch recent neuroscience articles
from multiple sources including arXiv, bioRxiv, and Springer Nature journals.
"""

import argparse
import datetime
import json
import jsonlines
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler_arxiv import (
    fetch_recent_arxiv_papers,
    save_arxiv_papers,
    NEUROSCIENCE_CATEGORY
)
from crawler_biorxiv import (
    fetch_recent_biorxiv_papers,
    save_biorxiv_papers
)
from crawler_nature import (
    process_nature_article_infos
)
from crawler_science import fetch_science_papers

# Default configuration
DEFAULT_DAYS = 7
DEFAULT_OUTPUT_DIR = "getfiles"

# Nature journal URLs to crawl
NATURE_JOURNALS = [
    'https://www.nature.com/nature/research-articles',
    'https://www.nature.com/nature/reviews-and-analysis',
    'https://www.nature.com/natbiomedeng/research-articles',
    'https://www.nature.com/natbiomedeng/reviews-and-analysis',
    'https://www.nature.com/nmeth/research-articles',
    'https://www.nature.com/nmeth/reviews-and-analysis',
    'https://www.nature.com/neuro/research-articles',
    'https://www.nature.com/neuro/reviews-and-analysis',
    'https://www.nature.com/nathumbehav/research-articles',
    'https://www.nature.com/nathumbehav/reviews-and-analysis',
]


def fetch_all_arxiv_papers(days: int = DEFAULT_DAYS, max_results: int = 50) -> List[Dict]:
    """Fetch papers from arXiv."""
    print("\n" + "=" * 80)
    print("Fetching from arXiv (q-bio.NC - Neurons and Cognition)...")
    print("=" * 80)
    
    papers = fetch_recent_arxiv_papers(
        days=days,
        categories=[NEUROSCIENCE_CATEGORY],
        max_results_per_category=max_results
    )
    
    print(f"Total arXiv papers: {len(papers)}")
    return papers


def fetch_all_biorxiv_papers(days: int = DEFAULT_DAYS, max_results: int = 200) -> List[Dict]:
    """Fetch papers from bioRxiv."""
    print("\n" + "=" * 80)
    print("Fetching from bioRxiv...")
    print("=" * 80)
    
    papers = fetch_recent_biorxiv_papers(
        days=days,
        categories=None,  # Fetch all categories, filter by date
        max_results=max_results
    )
    
    print(f"Total bioRxiv papers: {len(papers)}")
    return papers


def fetch_all_nature_papers() -> List[Dict]:
    """Fetch papers from Nature journals."""
    print("\n" + "=" * 80)
    print("Fetching from Nature journals...")
    print("=" * 80)
    
    all_papers = []
    for idx, base_url in enumerate(NATURE_JOURNALS):
        print(f"\n[{idx + 1}/{len(NATURE_JOURNALS)}] Processing: {base_url}")
        try:
            papers = process_nature_article_infos(base_url)
            all_papers.extend(papers)
            print(f"  -> Found {len(papers)} papers")
        except Exception as e:
            print(f"  -> Error: {e}")
    
    print(f"\nTotal Nature papers: {len(all_papers)}")
    return all_papers


def fetch_all_science_papers() -> List[Dict]:
    """
    Fetch papers from Science journal.
    
    Uses list pages + Europe PMC enrichment to avoid captcha issues.
    """
    print("\n" + "=" * 80)
    print("Fetching from Science journal...")
    print("=" * 80)
    
    try:
        papers = fetch_science_papers(enrich=True, delay=0.5)
        print(f"\nTotal Science papers: {len(papers)}")
        
        # Show enrichment breakdown
        status_counts = {}
        for p in papers:
            status = p.get('enrichment_status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        if status_counts:
            print("\nEnrichment breakdown:")
            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")
        
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Science papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def merge_papers(*paper_lists: List[List[Dict]]) -> List[Dict]:
    """Merge papers from multiple sources, removing duplicates."""
    print("\n" + "=" * 80)
    print("Merging and deduplicating papers...")
    print("=" * 80)
    
    # Combine all papers
    all_papers = []
    for papers in paper_lists:
        all_papers.extend(papers)
    
    print(f"Total papers before deduplication: {len(all_papers)}")
    
    # Deduplicate based on title (case-insensitive)
    seen_titles = set()
    unique_papers = []
    duplicates = 0
    
    for paper in all_papers:
        title_key = paper.get('title', '').lower().strip()
        # Remove common punctuation for comparison
        title_key = ''.join(c for c in title_key if c.isalnum() or c.isspace())
        
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_papers.append(paper)
        else:
            duplicates += 1
    
    print(f"Duplicates removed: {duplicates}")
    print(f"Unique papers: {len(unique_papers)}")
    
    # Sort by date (newest first)
    def parse_date(paper: Dict) -> datetime.datetime:
        date_str = paper.get('date', '')
        try:
            # Try multiple date formats
            for fmt in ['%d %b %Y', '%Y-%m-%d', '%d %B %Y', '%b %d %Y']:
                try:
                    return datetime.datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            # If no format matches, return epoch
            return datetime.datetime.min
        except Exception:
            return datetime.datetime.min
    
    unique_papers.sort(key=parse_date, reverse=True)
    
    return unique_papers


def save_merged_papers(papers: List[Dict], output_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    """Save merged papers to JSONL file."""
    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
    filepath = os.path.join(output_dir, f'all_papers_{timestamp}.jsonl')
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"\nSaved merged papers to: {filepath}")
    print(f"File size: {os.path.getsize(filepath)} bytes")
    
    return filepath


def save_source_summary(arxiv_papers: List[Dict], biorxiv_papers: List[Dict], 
                        nature_papers: List[Dict], science_papers: List[Dict],
                        output_dir: str = DEFAULT_OUTPUT_DIR):
    """Save a summary of papers by source."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
    summary = {
        'date': timestamp,
        'sources': {
            'arxiv': {
                'count': len(arxiv_papers),
                'date_range': {
                    'min': min((p['date'] for p in arxiv_papers), default='N/A'),
                    'max': max((p['date'] for p in arxiv_papers), default='N/A')
                } if arxiv_papers else None
            },
            'biorxiv': {
                'count': len(biorxiv_papers),
                'date_range': {
                    'min': min((p['date'] for p in biorxiv_papers), default='N/A'),
                    'max': max((p['date'] for p in biorxiv_papers), default='N/A')
                } if biorxiv_papers else None
            },
            'nature': {
                'count': len(nature_papers),
                'date_range': {
                    'min': min((p['date'] for p in nature_papers), default='N/A'),
                    'max': max((p['date'] for p in nature_papers), default='N/A')
                } if nature_papers else None
            },
            'science': {
                'count': len(science_papers),
                'date_range': {
                    'min': min((p['date'] for p in science_papers), default='N/A'),
                    'max': max((p['date'] for p in science_papers), default='N/A')
                } if science_papers else None
            }
        }
    }
    
    filepath = os.path.join(output_dir, f'summary_{timestamp}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"Saved summary to: {filepath}")
    return filepath


def print_summary(arxiv_papers: List[Dict], biorxiv_papers: List[Dict], 
                  nature_papers: List[Dict], science_papers: List[Dict],
                  merged_papers: List[Dict]):
    """Print a formatted summary of the crawl results."""
    print("\n" + "=" * 80)
    print("CRAWL SUMMARY")
    print("=" * 80)
    
    print(f"\n{'Source':<20} {'Count':>10}")
    print("-" * 32)
    print(f"{'arXiv':<20} {len(arxiv_papers):>10}")
    print(f"{'bioRxiv':<20} {len(biorxiv_papers):>10}")
    print(f"{'Nature Journals':<20} {len(nature_papers):>10}")
    print(f"{'Science':<20} {len(science_papers):>10}")
    print("-" * 32)
    total_before = len(arxiv_papers) + len(biorxiv_papers) + len(nature_papers) + len(science_papers)
    print(f"{'Total (before dedup)':<20} {total_before:>10}")
    print(f"{'Unique papers':<20} {len(merged_papers):>10}")
    
    if merged_papers:
        print(f"\nDate range: {merged_papers[-1]['date']} to {merged_papers[0]['date']}")
        
        # Show sample papers
        print("\n" + "=" * 80)
        print("SAMPLE PAPERS (Newest 3)")
        print("=" * 80)
        for i, paper in enumerate(merged_papers[:3], 1):
            source = paper.get('source', 'Unknown')
            print(f"\n[{i}] [{source}] {paper['title'][:70]}...")
            print(f"    Authors: {', '.join(paper['authors'][:3])}{'...' if len(paper.get('authors', [])) > 3 else ''}")
            print(f"    Date: {paper['date']}")


def main():
    parser = argparse.ArgumentParser(
        description='Neuroscience Bulletin - Fetch latest neuroscience articles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py                          # Fetch from all sources
  python src/main.py --arxiv-only             # Fetch only from arXiv
  python src/main.py --biorxiv-only           # Fetch only from bioRxiv  
  python src/main.py --nature-only            # Fetch only from Nature journals
  python src/main.py --days 14                # Look back 14 days for preprints
  python src/main.py --no-merge               # Save separate files per source
        """
    )
    
    # Source selection
    parser.add_argument('--arxiv-only', action='store_true',
                        help='Fetch only from arXiv')
    parser.add_argument('--biorxiv-only', action='store_true',
                        help='Fetch only from bioRxiv')
    parser.add_argument('--nature-only', action='store_true',
                        help='Fetch only from Nature journals')
    parser.add_argument('--science-only', action='store_true',
                        help='Fetch only from Science journal (with Europe PMC enrichment)')
    
    # Configuration
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS,
                        help=f'Number of days to look back for preprints (default: {DEFAULT_DAYS})')
    parser.add_argument('--arxiv-limit', type=int, default=50,
                        help='Maximum arXiv papers to fetch (default: 50)')
    parser.add_argument('--biorxiv-limit', type=int, default=200,
                        help='Maximum bioRxiv papers to fetch (default: 200)')
    parser.add_argument('--output-dir', type=str, default=DEFAULT_OUTPUT_DIR,
                        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})')
    
    # Output options
    parser.add_argument('--no-merge', action='store_true',
                        help='Keep separate files per source instead of merging')
    parser.add_argument('--skip-dedup', action='store_true',
                        help='Skip deduplication step')
    

    
    args = parser.parse_args()
    
    # Determine which sources to fetch
    any_specific = args.arxiv_only or args.biorxiv_only or args.nature_only or args.science_only
    fetch_arxiv = args.arxiv_only or not any_specific
    fetch_biorxiv = args.biorxiv_only or not any_specific
    fetch_nature = args.nature_only or not any_specific
    fetch_science = args.science_only or not any_specific
    
    arxiv_papers = []
    biorxiv_papers = []
    nature_papers = []
    science_papers = []
    
    try:
        # Fetch from selected sources
        if fetch_arxiv:
            arxiv_papers = fetch_all_arxiv_papers(
                days=args.days,
                max_results=args.arxiv_limit
            )
            if args.no_merge:
                arxiv_filename = f"arxiv_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                save_arxiv_papers(arxiv_papers, 
                    os.path.join(args.output_dir, arxiv_filename))
        
        if fetch_biorxiv:
            biorxiv_papers = fetch_all_biorxiv_papers(
                days=args.days,
                max_results=args.biorxiv_limit
            )
            if args.no_merge:
                biorxiv_filename = f"biorxiv_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                save_biorxiv_papers(biorxiv_papers,
                    os.path.join(args.output_dir, biorxiv_filename))
        
        if fetch_nature:
            nature_papers = fetch_all_nature_papers()
        
        if fetch_science:
            science_papers = fetch_all_science_papers()
            if args.no_merge:
                import jsonlines
                science_filename = f"science_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, science_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in science_papers:
                        f.write(paper)
                print(f"\nSaved Science papers to: {filepath}")
        
        # Merge papers (unless --no-merge is specified)
        if not args.no_merge:
            if args.skip_dedup:
                # Simple merge without deduplication
                merged_papers = []
                merged_papers.extend(arxiv_papers)
                merged_papers.extend(biorxiv_papers)
                merged_papers.extend(nature_papers)
                merged_papers.extend(science_papers)
                # Sort by date
                def parse_date(paper: Dict) -> datetime.datetime:
                    date_str = paper.get('date', '')
                    try:
                        for fmt in ['%d %b %Y', '%Y-%m-%d', '%d %B %Y', '%b %d %Y']:
                            try:
                                return datetime.datetime.strptime(date_str, fmt)
                            except ValueError:
                                continue
                        return datetime.datetime.min
                    except Exception:
                        return datetime.datetime.min
                merged_papers.sort(key=parse_date, reverse=True)
            else:
                merged_papers = merge_papers(arxiv_papers, biorxiv_papers, nature_papers, science_papers)
            
            save_merged_papers(merged_papers, args.output_dir)
            save_source_summary(arxiv_papers, biorxiv_papers, nature_papers, science_papers, args.output_dir)
            print_summary(arxiv_papers, biorxiv_papers, nature_papers, science_papers, merged_papers)
        else:
            # Print summary without merge
            print("\n" + "=" * 80)
            print("CRAWL COMPLETE (Separate files saved)")
            print("=" * 80)
            print(f"arXiv: {len(arxiv_papers)} papers")
            print(f"bioRxiv: {len(biorxiv_papers)} papers")
            print(f"Nature: {len(nature_papers)} papers")
            print(f"Science: {len(science_papers)} papers")
        
        print("\n[OK] Done!")
        
    except KeyboardInterrupt:
        print("\n\n[WARN] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
