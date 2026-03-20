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
    NEUROSCIENCE_CATEGORIES
)
from crawler_biorxiv import (
    fetch_recent_biorxiv_papers,
    save_biorxiv_papers
)
from crawler_nature import (
    process_nature_article_infos
)
from crawler_science import fetch_science_papers
from crawler_cell import fetch_cell_papers, CELL_JOURNALS
from crawler_jneurophys import fetch_jneurophys_papers
from crawler_jneurosci import fetch_jneurosci_papers
from crawler_jcogn import fetch_jcogn_papers
from crawler_jvis import fetch_jvis_papers

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


def fetch_all_arxiv_papers(days: int = DEFAULT_DAYS, max_results: int = 999, use_extended: bool = False) -> List[Dict]:
    """Fetch papers from arXiv."""
    from crawler_arxiv import NEUROSCIENCE_CATEGORIES, EXTENDED_CATEGORIES
    
    categories = EXTENDED_CATEGORIES if use_extended else NEUROSCIENCE_CATEGORIES
    
    print("\n" + "=" * 80)
    print("Fetching from arXiv...")
    print(f"Categories: {', '.join(categories)}")
    print(f"Date range: last {days} days only (strict)")
    print("=" * 80)
    
    papers = fetch_recent_arxiv_papers(
        days=days,
        categories=categories,
        max_results_per_category=max_results,
        use_extended=use_extended,
        fallback_if_empty=False  # Strict date filtering - don't fetch outside date range
    )
    
    print(f"Total arXiv papers: {len(papers)}")
    return papers


def fetch_all_biorxiv_papers(days: int = DEFAULT_DAYS, max_results: int = 200) -> List[Dict]:
    """
    Fetch papers from bioRxiv.
    
    By default, only fetches from neuroscience category using server-side filtering.
    """
    print("\n" + "=" * 80)
    print("Fetching from bioRxiv (neuroscience category)...")
    print("=" * 80)
    
    papers = fetch_recent_biorxiv_papers(
        days=days,
        category='neuroscience',  # Server-side category filtering
        max_results=max_results
    )
    
    print(f"Total bioRxiv papers: {len(papers)}")
    return papers


def fetch_all_nature_papers(days: int = DEFAULT_DAYS) -> List[Dict]:
    """
    Fetch papers from Nature journals.
    
    Args:
        days: Only fetch articles from last N days
    """
    print("\n" + "=" * 80)
    print(f"Fetching from Nature journals (last {days} days)...")
    print("=" * 80)
    
    all_papers = []
    for idx, base_url in enumerate(NATURE_JOURNALS):
        print(f"\n[{idx + 1}/{len(NATURE_JOURNALS)}] Processing: {base_url}")
        try:
            papers = process_nature_article_infos(base_url, days_back=days, fetch_abstracts=True)
            all_papers.extend(papers)
            print(f"  -> Found {len(papers)} papers")
        except Exception as e:
            print(f"  -> Error: {e}")
    
    print(f"\nTotal Nature papers: {len(all_papers)}")
    return all_papers


def fetch_all_science_papers(days: int = DEFAULT_DAYS) -> List[Dict]:
    """
    Fetch papers from Science journal.
    
    Uses list pages + Europe PMC enrichment to avoid captcha issues.
    """
    print("\n" + "=" * 80)
    print("Fetching from Science journal...")
    print("=" * 80)
    
    try:
        papers = fetch_science_papers(enrich=True, delay=0.5, days=days)
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


def fetch_all_jneurosci_papers(days: int = DEFAULT_DAYS, include_journal_club: bool = False) -> List[Dict]:
    """
    Fetch papers from Journal of Neuroscience.
    
    Uses PubMed API to search for recent articles.
    By default, filters out Journal Club articles (Vol 46, Issue 11, no abstract).
    
    Args:
        days: Number of days to look back
        include_journal_club: Whether to include Journal Club articles
    """
    print("\n" + "=" * 80)
    print("Fetching from Journal of Neuroscience...")
    if not include_journal_club:
        print("(Journal Club articles will be filtered)")
    print("=" * 80)
    
    try:
        papers = fetch_jneurosci_papers(days=days, max_results=999, include_journal_club=include_journal_club)
        print(f"\nTotal Journal of Neuroscience papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Journal of Neuroscience papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_jneurophys_papers(days: int = DEFAULT_DAYS, use_both_sources: bool = True) -> List[Dict]:
    """
    Fetch papers from Journal of Neurophysiology.
    
    Uses PubMed API (primary) and Europe PMC (supplementary) for faster updates.
    Automatically deduplicates based on PMID.
    
    Args:
        days: Number of days to look back
        use_both_sources: Whether to also query Europe PMC for missing articles
    """
    print("\n" + "=" * 80)
    print("Fetching from Journal of Neurophysiology...")
    if use_both_sources:
        print("Using PubMed (primary) + Europe PMC (supplementary)")
    else:
        print("Using PubMed only")
    print("=" * 80)
    
    try:
        papers = fetch_jneurophys_papers(days=days, max_results=999, use_both_sources=use_both_sources)
        print(f"\nTotal Journal of Neurophysiology papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Journal of Neurophysiology papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_jcogn_papers(days: int = DEFAULT_DAYS) -> List[Dict]:
    """
    Fetch papers from Journal of Cognitive Neuroscience.
    
    Uses PubMed API to search for recent articles.
    """
    print("\n" + "=" * 80)
    print("Fetching from Journal of Cognitive Neuroscience...")
    print("=" * 80)
    
    try:
        papers = fetch_jcogn_papers(days=days, max_results=999)
        print(f"\nTotal Journal of Cognitive Neuroscience papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Journal of Cognitive Neuroscience papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_jvis_papers(days: int = DEFAULT_DAYS) -> List[Dict]:
    """
    Fetch papers from Journal of Vision.
    
    Uses PubMed API to search for recent articles.
    """
    print("\n" + "=" * 80)
    print("Fetching from Journal of Vision...")
    print("=" * 80)
    
    try:
        papers = fetch_jvis_papers(days=days, max_results=999)
        print(f"\nTotal Journal of Vision papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Journal of Vision papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_cell_papers() -> List[Dict]:
    """
    Fetch papers from Cell Press journals.
    
    Fetches from Neuron, Current Biology, and Trends in Neurosciences.
    Uses list pages + Europe PMC enrichment.
    """
    print("\n" + "=" * 80)
    print("Fetching from Cell Press journals...")
    print("=" * 80)
    
    # Focus on neuroscience-relevant journals
    journals = ['cell', 'neuron', 'current-biology', 'trends-neurosciences','cell-reports','iscience','cell-systems']
    
    try:
        papers = fetch_cell_papers(
            journals=journals,
            days=None,  # Don't filter by date, get all recent articles
            enrich=True,
            delay=0.5,
            headless=True
        )
        print(f"\nTotal Cell Press papers: {len(papers)}")
        
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
        print(f"[ERROR] Failed to fetch Cell Press papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def merge_papers(arxiv_papers: List[Dict], biorxiv_papers: List[Dict], 
                 nature_papers: List[Dict], science_papers: List[Dict],
                 cell_papers: List[Dict], jneurophys_papers: List[Dict],
                 jneurosci_papers: List[Dict], jcogn_papers: List[Dict],
                 jvis_papers: List[Dict]) -> List[Dict]:
    """Merge papers from multiple sources, removing duplicates."""
    print("\n" + "=" * 80)
    print("Merging and deduplicating papers...")
    print("=" * 80)
    
    # Combine all papers
    all_papers = []
    all_papers.extend(arxiv_papers)
    all_papers.extend(biorxiv_papers)
    all_papers.extend(nature_papers)
    all_papers.extend(science_papers)
    all_papers.extend(cell_papers)
    all_papers.extend(jneurophys_papers)
    all_papers.extend(jneurosci_papers)
    all_papers.extend(jcogn_papers)
    all_papers.extend(jvis_papers)
    
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
                        cell_papers: List[Dict], jneurophys_papers: List[Dict],
                        jneurosci_papers: List[Dict], jcogn_papers: List[Dict],
                        jvis_papers: List[Dict],
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
            },
            'cell': {
                'count': len(cell_papers),
                'date_range': {
                    'min': min((p['date'] for p in cell_papers), default='N/A'),
                    'max': max((p['date'] for p in cell_papers), default='N/A')
                } if cell_papers else None
            },
            'jneurophys': {
                'count': len(jneurophys_papers),
                'date_range': {
                    'min': min((p['date'] for p in jneurophys_papers), default='N/A'),
                    'max': max((p['date'] for p in jneurophys_papers), default='N/A')
                } if jneurophys_papers else None
            },
            'jneurosci': {
                'count': len(jneurosci_papers),
                'date_range': {
                    'min': min((p['date'] for p in jneurosci_papers), default='N/A'),
                    'max': max((p['date'] for p in jneurosci_papers), default='N/A')
                } if jneurosci_papers else None
            },
            'jcogn': {
                'count': len(jcogn_papers),
                'date_range': {
                    'min': min((p['date'] for p in jcogn_papers), default='N/A'),
                    'max': max((p['date'] for p in jcogn_papers), default='N/A')
                } if jcogn_papers else None
            },
            'jvis': {
                'count': len(jvis_papers),
                'date_range': {
                    'min': min((p['date'] for p in jvis_papers), default='N/A'),
                    'max': max((p['date'] for p in jvis_papers), default='N/A')
                } if jvis_papers else None
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
                  cell_papers: List[Dict], jneurophys_papers: List[Dict],
                  jneurosci_papers: List[Dict], jcogn_papers: List[Dict],
                  jvis_papers: List[Dict],
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
    print(f"{'Cell Press':<20} {len(cell_papers):>10}")
    print(f"{'Journal of Neurophys':<20} {len(jneurophys_papers):>10}")
    print(f"{'Journal of Neurosci':<20} {len(jneurosci_papers):>10}")
    print(f"{'J. Cognitive Neurosci':<20} {len(jcogn_papers):>10}")
    print(f"{'Journal of Vision':<20} {len(jvis_papers):>10}")
    print("-" * 32)
    total_before = len(arxiv_papers) + len(biorxiv_papers) + len(nature_papers) + len(science_papers) + len(cell_papers) + len(jneurophys_papers) + len(jneurosci_papers) + len(jcogn_papers) + len(jvis_papers)
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
  python src/main.py --arxiv-only             # Fetch from core arXiv categories (NC, TO, MN)
  python src/main.py --arxiv-only --extended  # Fetch from extended arXiv categories (+AI/CV/ML)
  python src/main.py --biorxiv-only           # Fetch only from bioRxiv  
  python src/main.py --nature-only            # Fetch only from Nature journals
  python src/main.py --science-only           # Fetch only from Science journal
  python src/main.py --cell-only              # Fetch only from Cell Press journals
  python src/main.py --jneurosci-only         # Fetch only from Journal of Neuroscience
  python src/main.py --jcogn-only             # Fetch only from Journal of Cognitive Neuroscience
  python src/main.py --jvis-only              # Fetch only from Journal of Vision
  python src/main.py --days 14                # Look back 14 days for all sources
  python src/main.py --no-merge               # Save separate files per source
        """
    )
    
    # Source selection
    parser.add_argument('--arxiv-only', action='store_true',
                        help='Fetch only from arXiv')
    parser.add_argument('--biorxiv-only', # action='store_true',
                        default=False,
                        help='Fetch only from bioRxiv')
    parser.add_argument('--nature-only', action='store_true',
                        help='Fetch only from Nature journals')
    parser.add_argument('--science-only', action='store_true',
                        help='Fetch only from Science journal (with Europe PMC enrichment)')
    parser.add_argument('--cell-only', action='store_true',
                        help='Fetch only from Cell Press journals (Neuron, Current Biology, etc.)')
    parser.add_argument('--jneurophys-only', action='store_true',
                        help='Fetch only from Journal of Neurophysiology')
    parser.add_argument('--jneurophys-pubmed-only', action='store_true',
                        help='Use only PubMed for Journal of Neurophysiology (skip Europe PMC)')
    parser.add_argument('--jneurosci-only', action='store_true',
                        help='Fetch only from Journal of Neuroscience')
    parser.add_argument('--include-journal-club', action='store_true',
                        help='Include Journal Club articles (default: filtered out)')
    parser.add_argument('--jcogn-only', action='store_true',
                        help='Fetch only from Journal of Cognitive Neuroscience')
    parser.add_argument('--jvis-only', action='store_true',
                        help='Fetch only from Journal of Vision')
    
    # Configuration
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS,
                        help=f'Number of days to look back for all sources (default: {DEFAULT_DAYS})')
    parser.add_argument('--arxiv-limit', type=int, default=999,
                        help='Maximum arXiv papers to fetch per category (default: 999)')
    parser.add_argument('--biorxiv-limit', type=int, default=200,
                        help='Maximum bioRxiv papers to fetch (default: 200)')
    parser.add_argument('--extended', action='store_true',
                        help='Use extended arXiv categories (includes cs.AI, cs.CV, cs.LG, etc.)')
    parser.add_argument('--output-dir', type=str, default=DEFAULT_OUTPUT_DIR,
                        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})')
    
    # Output options
    parser.add_argument('--no-merge', action='store_true',
                        help='Keep separate files per source instead of merging')
    parser.add_argument('--skip-dedup', action='store_true',
                        help='Skip deduplication step')
    

    
    args = parser.parse_args()
    
    # Determine which sources to fetch
    any_specific = args.arxiv_only or args.biorxiv_only or args.nature_only or args.science_only or args.cell_only or args.jneurophys_only or args.jneurosci_only or args.jcogn_only or args.jvis_only
    fetch_arxiv = args.arxiv_only or not any_specific
    fetch_biorxiv = False #args.biorxiv_only or not any_specific
    fetch_nature = args.nature_only or not any_specific
    fetch_science = args.science_only or not any_specific
    fetch_cell = args.cell_only or not any_specific
    fetch_jneurophys = args.jneurophys_only or not any_specific
    fetch_jneurosci = args.jneurosci_only or not any_specific
    fetch_jcogn = args.jcogn_only or not any_specific
    fetch_jvis = args.jvis_only or not any_specific
    
    arxiv_papers = []
    biorxiv_papers = []
    jcogn_papers = []
    jvis_papers = []
    nature_papers = []
    science_papers = []
    cell_papers = []
    jneurophys_papers = []
    jneurosci_papers = []
    
    try:
        # Fetch from selected sources
        if fetch_arxiv:
            arxiv_papers = fetch_all_arxiv_papers(
                days=args.days,
                max_results=args.arxiv_limit,
                use_extended=args.extended
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
            nature_papers = fetch_all_nature_papers(days=args.days)
        
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
        
        if fetch_cell:
            cell_papers = fetch_all_cell_papers()
            if args.no_merge:
                import jsonlines
                cell_filename = f"cell_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, cell_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in cell_papers:
                        f.write(paper)
                print(f"\nSaved Cell Press papers to: {filepath}")
        
        if fetch_jneurophys:
            jneurophys_papers = fetch_all_jneurophys_papers(days=args.days, use_both_sources=not args.jneurophys_pubmed_only)
            if args.no_merge:
                import jsonlines
                jneurophys_filename = f"jneurophys_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jneurophys_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jneurophys_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Neurophysiology papers to: {filepath}")
        
        if fetch_jneurosci:
            jneurosci_papers = fetch_all_jneurosci_papers(days=args.days, include_journal_club=args.include_journal_club)
            if args.no_merge:
                import jsonlines
                jneurosci_filename = f"jneurosci_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jneurosci_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jneurosci_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Neuroscience papers to: {filepath}")
        
        if fetch_jcogn:
            jcogn_papers = fetch_all_jcogn_papers(days=args.days)
            if args.no_merge:
                import jsonlines
                jcogn_filename = f"jcogn_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jcogn_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jcogn_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Cognitive Neuroscience papers to: {filepath}")
        
        if fetch_jvis:
            jvis_papers = fetch_all_jvis_papers(days=args.days)
            if args.no_merge:
                import jsonlines
                jvis_filename = f"jvis_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jvis_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jvis_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Vision papers to: {filepath}")
        
        # Merge papers (unless --no-merge is specified)
        if not args.no_merge:
            if args.skip_dedup:
                # Simple merge without deduplication
                merged_papers = []
                merged_papers.extend(arxiv_papers)
                merged_papers.extend(biorxiv_papers)
                merged_papers.extend(nature_papers)
                merged_papers.extend(science_papers)
                merged_papers.extend(cell_papers)
                merged_papers.extend(jneurophys_papers)
                merged_papers.extend(jneurosci_papers)
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
                merged_papers = merge_papers(arxiv_papers, biorxiv_papers, nature_papers, science_papers, cell_papers, jneurophys_papers, jneurosci_papers, jcogn_papers, jvis_papers)
            
            save_merged_papers(merged_papers, args.output_dir)
            save_source_summary(arxiv_papers, biorxiv_papers, nature_papers, science_papers, cell_papers, jneurophys_papers, jneurosci_papers, jcogn_papers, jvis_papers, args.output_dir)
            print_summary(arxiv_papers, biorxiv_papers, nature_papers, science_papers, cell_papers, jneurophys_papers, jneurosci_papers, jcogn_papers, jvis_papers, merged_papers)
        else:
            # Print summary without merge
            print("\n" + "=" * 80)
            print("CRAWL COMPLETE (Separate files saved)")
            print("=" * 80)
            print(f"arXiv: {len(arxiv_papers)} papers")
            print(f"bioRxiv: {len(biorxiv_papers)} papers")
            print(f"Nature: {len(nature_papers)} papers")
            print(f"Science: {len(science_papers)} papers")
            print(f"Cell Press: {len(cell_papers)} papers")
            print(f"Journal of Neurophysiology: {len(jneurophys_papers)} papers")
            print(f"Journal of Neuroscience: {len(jneurosci_papers)} papers")
            print(f"Journal of Cognitive Neuroscience: {len(jcogn_papers)} papers")
            print(f"Journal of Vision: {len(jvis_papers)} papers")
        
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
