"""
ROR Batch Refine - Re-normalize affiliations with local ROR matching

Usage:
    python src/ror_refine_batch.py input_enriched.jsonl
    python src/ror_refine_batch.py input_enriched.jsonl -o output_refined.jsonl
    python src/ror_refine_batch.py input_enriched.jsonl --threshold 85
"""

import argparse
import jsonlines
import json
import os
import time
from typing import List, Dict
import tqdm

from supp_func import ROR_Search


def ror_refine_paper(paper: Dict, ror_search: ROR_Search) -> Dict:
    """Refine affiliations in one paper with ROR matching."""
    if not paper.get('author_details'):
        return paper
    
    for idx, author in enumerate(paper['author_details']):
        affiliations = author.get('affiliation')
        if not affiliations:
            continue
        if isinstance(affiliations, str):
            affiliations = affiliations.split(';')
        paper['author_details'][idx]['ror_normalized_affiliation'] = []
        paper['author_details'][idx]['ror_match_score'] = []
        paper['author_details'][idx]['ror_country'] = []
        paper['author_details'][idx]['ror_subregion'] = []
        for affiliation in affiliations:
            standard_name, score, location_info = ror_search.extract_institute_info(affiliation)
            if standard_name and score >= ror_search.threshold:
                paper['author_details'][idx]['ror_normalized_affiliation'].append(standard_name)
                paper['author_details'][idx]['ror_match_score'].append(score)
            if location_info[0] is not None:
                paper['author_details'][idx]['ror_country'].append(location_info[0])
            if location_info[1] is not None:
                paper['author_details'][idx]['ror_subregion'].append(location_info[1])
            if location_info[0] is None:
                print(f"\nno country detected for {affiliation}")
                print(f"affiliation = {affiliation}, -> {location_info}")
    return paper


def ror_refine_batch(input_file: str, output_file: str = None, threshold: int = 90) -> str:
    """
    Refine all papers in batch with ROR matching.
    
    Args:
        input_file: Input enriched JSONL file
        output_file: Output refined JSONL file (default: input_ror_refined.jsonl)
        threshold: ROR matching threshold
    
    Returns:
        Output file path
    """
    if output_file is None:
        base, ext = os.path.splitext(input_file)
        output_file = f"{base}_ror_refined{ext}"
    
    print("=" * 80)
    print("ROR Batch Refine - Re-normalize affiliations with local ROR matching")
    print("=" * 80)
    print(f"Input:       {input_file}")
    print(f"Output:      {output_file}")
    print(f"Threshold:   {threshold}")
    print()
    
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return ""
    
    print("Loading ROR index...")
    start_time = time.time()
    ror_search = ROR_Search(threshold=threshold)
    print(f"ROR index loaded in {time.time() - start_time:.2f}s")
    print(f"  - Standard names: {len(ror_search.standard_name_dict)}")
    print(f"  - Aliases: {len(ror_search.alias_name_dict)}")
    print()
    
    print("Loading input papers...")
    try:
        with jsonlines.open(input_file) as f:
            papers = list(f)
    except Exception as e:
        print(f"[ERROR] Failed to load input: {e}")
        return ""
    
    total_papers = len(papers)
    print(f"Loaded {total_papers} papers")
    print()
    
    print("Starting ROR refinement...")
    start_time = time.time()
    
    total_affiliations = 0
    matched_affiliations = 0
    
    refined_papers = []
    for i, paper in enumerate(tqdm.tqdm(papers), 1):        
        if paper.get('author_details') or paper.get('authors_enriched'):
            authors = paper.get('author_details', paper.get('authors_enriched', []))
            for author in authors:
                if author.get('affiliation'):
                    total_affiliations += 1
        
        refined_paper = ror_refine_paper(paper, ror_search)
        refined_papers.append(refined_paper)
        
        for author in refined_paper.get('author_details', []):
            if 'ror_normalized_affiliation' in author:
                matched_affiliations += 1
    
    elapsed = time.time() - start_time
    
    print(f"\nSaving to {output_file}...")
    try:
        with jsonlines.open(output_file, 'w') as f:
            for paper in refined_papers:
                f.write(paper)
    except Exception as e:
        print(f"[ERROR] Failed to save output: {e}")
        return ""
    
    print("\n" + "=" * 80)
    print("REFINEMENT COMPLETE")
    print("=" * 80)
    print(f"Total papers:     {total_papers}")
    print(f"Total affiliations checked: {total_affiliations}")
    print(f"Successfully matched with ROR: {matched_affiliations} "
          f"({matched_affiliations/max(1, total_affiliations)*100:.1f}%)")
    print(f"Processing time:  {elapsed:.1f}s "
          f"({elapsed/max(1, total_papers):.2f}s per paper)")
    print(f"\nOutput saved to: {output_file}")
    print('example of refined paper')
    # Handle Unicode encoding for Windows PowerShell
    # try:
    #     print(json.dumps(refined_papers[0], ensure_ascii=False, indent=2))
    # except UnicodeEncodeError:
    #     # Convert to ASCII with replacement for non-ASCII characters
    #     print(json.dumps(refined_papers[0], ensure_ascii=True, indent=2))
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='ROR Batch Refine - Re-normalize affiliations with local ROR matching',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/ror_refine_batch.py getfiles/all_papers_2026-04-11_enriched.jsonl
  python src/ror_refine_batch.py input.jsonl -o output.jsonl
  python src/ror_refine_batch.py input.jsonl --threshold 85
        """
    )
    
    parser.add_argument('--input', help='Input enriched JSONL file path', default="./getfiles/all_papers_2026-03-14_enriched.jsonl" )
    parser.add_argument('-o', '--output', help='Output JSONL file path (default: input_ror_refined.jsonl)')
    parser.add_argument('--threshold', type=int, default=90, 
                        help=f'ROR matching score threshold (default: 90)')
    
    args = parser.parse_args()
    
    ror_refine_batch(args.input, args.output, args.threshold)


if __name__ == '__main__':
    main()
