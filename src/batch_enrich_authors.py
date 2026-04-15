"""
Batch Author Enrichment V2 - Concurrent + Batch Optimized

Usage:
    python batch_enrich_v2.py input.jsonl
    python batch_enrich_v2.py input.jsonl -o output.jsonl
    python batch_enrich_v2.py input.jsonl -w 10  # Use 10 workers
"""

import argparse
import jsonlines
import sys
import os
from pathlib import Path
from datetime import datetime
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enrich_authors import enrich_papers_concurrent, get_db


def batch_enrich(input_file: str, output_file: str = None, max_workers: int = 5, limit: int = None):
    """
    Batch enrich papers with concurrent processing
    
    Args:
        input_file: Input JSONL path
        output_file: Output JSONL path (default: input_enriched.jsonl)
        max_workers: Max concurrent threads
        limit: Limit number of papers (for testing)
    """
    # Determine output filename
    if output_file is None:
        base, ext = os.path.splitext(input_file)
        if '_enriched' in base:
            output_file = input_file
        else:
            output_file = f"{base}_enriched{ext}"
    
    print("=" * 80)
    print("Batch Author Enrichment V2 - Concurrent + Batch Optimized")
    print("=" * 80)
    print(f"Input:       {input_file}")
    print(f"Output:      {output_file}")
    print(f"Workers:     {max_workers}")
    if limit:
        print(f"Limit:       {limit} papers")
    print()
    
    # Check input
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return None
    
    # Load papers
    print("Loading papers...")
    try:
        with jsonlines.open(input_file) as f:
            papers = list(f)
    except Exception as e:
        print(f"[ERROR] Failed to load: {e}")
        return None
    
    total = len(papers)
    if total == 0:
        print("[ERROR] No papers found")
        return None
    
    if limit:
        papers = papers[:limit]
        print(f"Loaded {total} papers, processing first {limit}")
    else:
        print(f"Loaded {total} papers")
    
    # Process
    start_time = time.time()
    
    try:
        enriched_papers = enrich_papers_concurrent(papers, max_workers=max_workers)
    except Exception as e:
        print(f"\n[ERROR] Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    elapsed = time.time() - start_time
    
    # Save results
    print(f"\nSaving results to {output_file}...")
    try:
        with jsonlines.open(output_file, 'w') as f:
            for p in enriched_papers:
                f.write(p)
        print("[OK] Saved successfully")
    except Exception as e:
        print(f"[ERROR] Failed to save: {e}")
        return None
    
    # Statistics
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"Total papers:     {len(enriched_papers)}")
    print(f"Processing time:  {elapsed:.1f}s ({elapsed/len(enriched_papers):.1f}s per paper)")
    
    success_count = sum(1 for p in enriched_papers if p.get('author_enrichment_status') == 'enriched')
    senior_count = sum(p.get('senior_author_count', 0) for p in enriched_papers)
    papers_with_senior = sum(1 for p in enriched_papers if p.get('has_senior_researcher'))
    
    print(f"Successfully enriched: {success_count}")
    print(f"Papers with seniors:   {papers_with_senior} ({papers_with_senior/max(1,len(enriched_papers))*100:.1f}%)")
    print(f"Total senior authors:  {senior_count}")
    
    # Database stats
    db = get_db()
    print("\n" + "=" * 80)
    print("DATABASE STATISTICS")
    print("=" * 80)
    print(f"Cached authors: {len(db.authors)}")
    
    if db.authors:
        print("\nTop senior researchers:")
        sorted_authors = sorted(
            [(name, data) for name, data in db.authors.items() if (data.get('h_index') or 0) >= 25],
            key=lambda x: x[1].get('h_index') or 0,
            reverse=True
        )[:15]
        
        for name, data in sorted_authors:
            h_idx = data.get('h_index', 'N/A')
            cites = data.get('citations', 'N/A')
            warn = " [!]" if data.get('warning') else ""
            print(f"  - {name:<30} h={h_idx:<4} cites={cites}{warn}")
    
    print(f"\nOutput saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Batch enrich paper authors (V2 - Concurrent + Batch Optimized)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_enrich_v2.py getfiles/all_papers_2026-04-11.jsonl
  python batch_enrich_v2.py input.jsonl -o output.jsonl
  python batch_enrich_v2.py input.jsonl -w 10 -l 50
        """
    )
    
    parser.add_argument('input', help='Input JSONL file path')
    parser.add_argument('-o', '--output', help='Output JSONL file path')
    parser.add_argument('-w', '--workers', type=int, default=5, help='Max concurrent workers (default: 5)')
    parser.add_argument('-l', '--limit', type=int, help='Limit number of papers to process')
    
    args = parser.parse_args()
    
    batch_enrich(args.input, args.output, args.workers, args.limit)


if __name__ == '__main__':
    main()
