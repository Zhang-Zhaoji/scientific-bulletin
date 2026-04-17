"""
Neuroscience Bulletin - Main Entry Point (BETA with Integrated Enrichment)

This script coordinates all journal crawlers to fetch recent neuroscience articles
from multiple sources including arXiv, bioRxiv, and Springer Nature journals.
INTEGRATED: Automatic author enrichment + ROR institution name normalization
"""

import argparse
import datetime
import json
import jsonlines
import os
import sys
import time
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
from crawler_pnas import fetch_pnas_papers
from crawler_natcomm import fetch_natcomm_papers
from crawler_brain import fetch_brain_papers
from crawler_sciadv import fetch_sciadv_papers
from crawler_elife import fetch_elife_papers

# Import for enrichment
from enrich_authors import enrich_papers_concurrent, get_database
from supp_func import ROR_Search

# Default configuration
DEFAULT_DAYS = 7
DEFAULT_OUTPUT_DIR = "getfiles"
DEFAULT_WORKERS = 5
DEFAULT_ROR_THRESHOLD = 90

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
        fallback_if_empty=False
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
        category='neuroscience',
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


def fetch_all_pnas_papers(days: int = DEFAULT_DAYS) -> List[Dict]:
    """
    Fetch papers from PNAS.

    Uses PubMed API to search for recent articles.
    """
    print("\n" + "=" * 80)
    print("Fetching from PNAS...")
    print("=" * 80)

    try:
        papers = fetch_pnas_papers(days=days, max_results=999)
        print(f"\nTotal PNAS papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch PNAS papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_natcomm_papers(days: int = DEFAULT_DAYS, enrich: bool = True) -> List[Dict]:
    """
    Fetch papers from Nature Communications.

    Uses subject pages (Biological Sciences, Health Sciences) to filter
    for biology/health-related articles only, avoiding physics/chemistry/materials.
    """
    print("\n" + "=" * 80)
    print("Fetching from Nature Communications...")
    print("Sources: Biological Sciences, Health Sciences")
    print("=" * 80)

    try:
        papers = fetch_natcomm_papers(days=days, max_results=200, enrich=enrich)
        print(f"\nTotal Nature Communications papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Nature Communications papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_brain_papers(days: int = DEFAULT_DAYS) -> List[Dict]:
    """
    Fetch papers from Brain.

    Uses PubMed API to search for recent articles.
    """
    print("\n" + "=" * 80)
    print("Fetching from Brain...")
    print("=" * 80)

    try:
        papers = fetch_brain_papers(days=days, max_results=999)
        print(f"\nTotal Brain papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Brain papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_sciadv_papers(days: int = DEFAULT_DAYS, enrich: bool = True, headless: bool = True) -> List[Dict]:
    """
    Fetch papers from Science Advances.

    Uses TOC page with Selenium to bypass anti-bot protection.
    Note: Science Advances website doesn't have working section filters,
    so we fetch from TOC and filter by date.
    """
    print("\n" + "=" * 80)
    print("Fetching from Science Advances...")
    print("=" * 80)

    try:
        papers = fetch_sciadv_papers(days=days, max_results=100, enrich=enrich, headless=headless)
        print(f"\nTotal Science Advances papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch Science Advances papers: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_all_elife_papers(days: int = DEFAULT_DAYS) -> List[Dict]:
    """
    Fetch papers from eLife.

    Uses PubMed API to search for recent articles.
    """
    print("\n" + "=" * 80)
    print("Fetching from eLife...")
    print("=" * 80)

    try:
        papers = fetch_elife_papers(days=days, max_results=999)
        print(f"\nTotal eLife papers: {len(papers)}")
        return papers
    except Exception as e:
        print(f"[ERROR] Failed to fetch eLife papers: {e}")
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

    journals = ['cell', 'neuron', 'current-biology', 'trends-neurosciences','cell-reports','iscience','cell-systems']

    try:
        papers = fetch_cell_papers(
            journals=journals,
            days=None,
            enrich=True,
            delay=0.5,
            headless=True
        )
        print(f"\nTotal Cell Press papers: {len(papers)}")

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
                 jvis_papers: List[Dict], pnas_papers: List[Dict],
                 natcomm_papers: List[Dict], brain_papers: List[Dict],
                 sciadv_papers: List[Dict], elife_papers: List[Dict]) -> List[Dict]:
    """Merge papers from multiple sources, removing duplicates."""
    print("\n" + "=" * 80)
    print("Merging and deduplicating papers...")
    print("=" * 80)

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
    all_papers.extend(pnas_papers)
    all_papers.extend(natcomm_papers)
    all_papers.extend(brain_papers)
    all_papers.extend(sciadv_papers)
    all_papers.extend(elife_papers)

    print(f"Total papers before deduplication: {len(all_papers)}")

    seen_titles = set()
    unique_papers = []
    duplicates = 0

    for paper in all_papers:
        title_key = paper.get('title', '').lower().strip()
        title_key = ''.join(c for c in title_key if c.isalnum() or c.isspace())

        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_papers.append(paper)
        else:
            duplicates += 1

    print(f"Duplicates removed: {duplicates}")
    print(f"Unique papers: {len(unique_papers)}")

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

    unique_papers.sort(key=parse_date, reverse=True)

    return unique_papers


def save_merged_papers(papers: List[Dict], output_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    """Save merged papers to JSONL file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
    filepath = os.path.join(output_dir, f'all_papers_{timestamp}.jsonl')

    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)

    print(f"\nSaved raw merged papers to: {filepath}")
    print(f"File size: {os.path.getsize(filepath)} bytes")

    return filepath


def save_enriched_papers(papers: List[Dict], output_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    """Save enriched papers to JSONL file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
    filepath = os.path.join(output_dir, f'all_papers_{timestamp}_enriched.jsonl')

    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)

    print(f"\nSaved enriched papers to: {filepath}")
    print(f"File size: {os.path.getsize(filepath)} bytes")

    return filepath


def save_source_summary(arxiv_papers: List[Dict], biorxiv_papers: List[Dict],
                        nature_papers: List[Dict], science_papers: List[Dict],
                        cell_papers: List[Dict], jneurophys_papers: List[Dict],
                        jneurosci_papers: List[Dict], jcogn_papers: List[Dict],
                        jvis_papers: List[Dict], pnas_papers: List[Dict],
                        natcomm_papers: List[Dict], brain_papers: List[Dict],
                        sciadv_papers: List[Dict], elife_papers: List[Dict],
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
            },
            'pnas': {
                'count': len(pnas_papers),
                'date_range': {
                    'min': min((p['date'] for p in pnas_papers), default='N/A'),
                    'max': max((p['date'] for p in pnas_papers), default='N/A')
                } if pnas_papers else None
            },
            'natcomm': {
                'count': len(natcomm_papers),
                'date_range': {
                    'min': min((p['date'] for p in natcomm_papers), default='N/A'),
                    'max': max((p['date'] for p in natcomm_papers), default='N/A')
                } if natcomm_papers else None
            },
            'brain': {
                'count': len(brain_papers),
                'date_range': {
                    'min': min((p['date'] for p in brain_papers), default='N/A'),
                    'max': max((p['date'] for p in brain_papers), default='N/A')
                } if brain_papers else None
            },
            'sciadv': {
                'count': len(sciadv_papers),
                'date_range': {
                    'min': min((p['date'] for p in sciadv_papers), default='N/A'),
                    'max': max((p['date'] for p in sciadv_papers), default='N/A')
                } if sciadv_papers else None
            },
            'elife': {
                'count': len(elife_papers),
                'date_range': {
                    'min': min((p['date'] for p in elife_papers), default='N/A'),
                    'max': max((p['date'] for p in elife_papers), default='N/A')
                } if elife_papers else None
            },
        }
    }

    filepath = os.path.join(output_dir, f'summary_{timestamp}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nSaved source summary to: {filepath}")


def print_summary(arxiv_papers: List[Dict], biorxiv_papers: List[Dict],
                  nature_papers: List[Dict], science_papers: List[Dict],
                  cell_papers: List[Dict], jneurophys_papers: List[Dict],
                  jneurosci_papers: List[Dict], jcogn_papers: List[Dict],
                  jvis_papers: List[Dict], pnas_papers: List[Dict],
                  natcomm_papers: List[Dict], brain_papers: List[Dict],
                  sciadv_papers: List[Dict], elife_papers: List[Dict],
                  merged_papers: List[Dict]):
    """Print final summary."""
    print("\n" + "=" * 80)
    print("CRAWL COMPLETE")
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
    print(f"PNAS: {len(pnas_papers)} papers")
    print(f"Nature Communications: {len(natcomm_papers)} papers")
    print(f"Brain: {len(brain_papers)} papers")
    print(f"Science Advances: {len(sciadv_papers)} papers")
    print(f"eLife: {len(elife_papers)} papers")
    print(f"-> Total merged: {len(merged_papers)} papers")


def normalize_affiliations_with_ror(enriched_papers: List[Dict], ror_search: ROR_Search) -> List[Dict]:
    """Use ROR local matching to normalize institution names in enriched papers."""
    print("\n" + "=" * 80)
    print("ROR Institution Name Normalization")
    print("=" * 80)

    total_affiliations = 0
    matched_affiliations = 0

    for paper in enriched_papers:
        if not paper.get('authors_enriched'):
            continue

        for author in paper['authors_enriched']:
            total_affiliations += 1
            affiliation = author.get('affiliation')

            if not affiliation:
                continue

            standard_name, score, location_info = ror_search.extract_institute_info(affiliation)

            if standard_name and score >= ror_search.threshold:
                author['ror_normalized_affiliation'] = standard_name
                author['ror_match_score'] = score
                if location_info[0] is not None:
                    author['ror_country'] = location_info[0]
                if location_info[1] is not None:
                    author['ror_subregion'] = location_info[1]
                matched_affiliations += 1

    print(f"Total affiliations: {total_affiliations}")
    print(f"Matched with ROR: {matched_affiliations} ({matched_affiliations/max(1, total_affiliations)*100:.1f}%)")

    return enriched_papers


def print_enrichment_statistics(enriched_papers: List[Dict]):
    """Print enrichment statistics."""
    print("\n" + "=" * 80)
    print("ENRICHMENT STATISTICS")
    print("=" * 80)

    total_papers = len(enriched_papers)
    success_count = sum(1 for p in enriched_papers if p.get('author_enrichment_status') == 'enriched')
    senior_count = sum(p.get('senior_author_count', 0) for p in enriched_papers)
    papers_with_senior = sum(1 for p in enriched_papers if p.get('has_senior_researcher'))

    print(f"Total papers:     {total_papers}")
    print(f"Successfully enriched: {success_count} ({success_count/max(1,total_papers)*100:.1f}%)")
    print(f"Papers with seniors:   {papers_with_senior} ({papers_with_senior/max(1,total_papers)*100:.1f}%)")
    print(f"Total senior authors:  {senior_count}")

    db = get_database()
    print("\n" + "=" * 80)
    print("DATABASE STATISTICS")
    print("=" * 80)
    print(f"Cached authors: {len(db.authors)}")


def main():
    parser = argparse.ArgumentParser(
        description='Neuroscience Bulletin - Main Entry Point (BETA with Integrated Enrichment)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main_beta.py                                    # Crawl all + auto-enrich (one-step)
  python src/main_beta.py --days 14 --workers 10             # 14 days, 10 concurrent workers
  python src/main_beta.py --arxiv-only --biorxiv-only        # Only preprints
  python src/main_beta.py --no-auto-enrich                   # Crawl only, skip enrichment
  python src/main_beta.py --ror-threshold 85                 # Lower ROR matching threshold
        """
    )

    parser.add_argument('--days', type=int, default=DEFAULT_DAYS,
                        help=f'Number of days to look back (default: {DEFAULT_DAYS})')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR,
                        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS,
                        help=f'Max concurrent workers for enrichment (default: {DEFAULT_WORKERS})')
    parser.add_argument('--ror-threshold', type=int, default=DEFAULT_ROR_THRESHOLD,
                        help=f'ROR matching score threshold (default: {DEFAULT_ROR_THRESHOLD})')
    parser.add_argument('--no-auto-enrich', action='store_true',
                        help='Skip automatic author enrichment (output raw only)')
    parser.add_argument('--no-merge', action='store_true',
                        help='Save separate files per source, do not merge')
    parser.add_argument('--skip-dedup', action='store_true',
                        help='Skip deduplication when merging')
    parser.add_argument('--arxiv-only', action='store_true', help='Only fetch from arXiv')
    parser.add_argument('--biorxiv-only', action='store_true', help='Only fetch from bioRxiv')
    parser.add_argument('--nature-only', action='store_true', help='Only fetch from Nature journals')
    parser.add_argument('--science-only', action='store_true', help='Only fetch from Science')
    parser.add_argument('--cell-only', action='store_true', help='Only fetch from Cell Press')
    parser.add_argument('--jneurophys-only', action='store_true', help='Only fetch from Journal of Neurophysiology')
    parser.add_argument('--jneurosci-only', action='store_true', help='Only fetch from Journal of Neuroscience')
    parser.add_argument('--jcogn-only', action='store_true', help='Only fetch from Journal of Cognitive Neuroscience')
    parser.add_argument('--jvis-only', action='store_true', help='Only fetch from Journal of Vision')
    parser.add_argument('--pnas-only', action='store_true', help='Only fetch from PNAS')
    parser.add_argument('--natcomm-only', action='store_true', help='Only fetch from Nature Communications')
    parser.add_argument('--brain-only', action='store_true', help='Only fetch from Brain')
    parser.add_argument('--sciadv-only', action='store_true', help='Only fetch from Science Advances')
    parser.add_argument('--elife-only', action='store_true', help='Only fetch from eLife')
    parser.add_argument('--include-journal-club', action='store_true',
                        help='Include Journal Club articles in Journal of Neuroscience')
    parser.add_argument('--jneurophys-pubmed-only', action='store_true',
                        help='Only use PubMed for Journal of Neurophysiology (faster, no Europe PMC)')
    parser.add_argument('--use-extended-arxiv', action='store_true',
                        help='Use extended arXiv categories (more categories)')
    parser.add_argument('--headless', default='true',
                        help='Run Selenium in headless mode (true/false, default: true)')

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("Neuroscience Bulletin - BETA with Integrated Enrichment")
    print("=" * 80)
    print(f"Date range: last {args.days} days")
    print(f"Output directory: {args.output_dir}")
    if not args.no_auto_enrich:
        print(f"Auto-enrichment: ENABLED (workers: {args.workers})")
        print(f"ROR normalization: ENABLED (threshold: {args.ror_threshold})")
    else:
        print(f"Auto-enrichment: DISABLED")
    print()

    try:
        arxiv_papers = []
        biorxiv_papers = []
        nature_papers = []
        science_papers = []
        cell_papers = []
        jneurophys_papers = []
        jneurosci_papers = []
        jcogn_papers = []
        jvis_papers = []
        pnas_papers = []
        natcomm_papers = []
        brain_papers = []
        sciadv_papers = []
        elife_papers = []

        fetch_all = not any([
            args.arxiv_only, args.biorxiv_only, args.nature_only, args.science_only,
            args.cell_only, args.jneurophys_only, args.jneurosci_only, args.jcogn_only,
            args.jvis_only, args.pnas_only, args.natcomm_only, args.brain_only,
            args.sciadv_only, args.elife_only
        ])

        if fetch_all or args.arxiv_only:
            max_results = 999 if fetch_all else 999
            arxiv_papers = fetch_all_arxiv_papers(
                days=args.days,
                max_results=max_results,
                use_extended=args.use_extended_arxiv
            )

        if fetch_all or args.biorxiv_only:
            max_results = 200 if fetch_all else 500
            biorxiv_papers = fetch_all_biorxiv_papers(days=args.days, max_results=max_results)

        if fetch_all or args.nature_only:
            nature_papers = fetch_all_nature_papers(days=args.days)

        if fetch_all or args.science_only:
            science_papers = fetch_all_science_papers(days=args.days)

        if fetch_all or args.cell_only:
            cell_papers = fetch_all_cell_papers()

        if fetch_all or args.jneurophys_only:
            use_both = not args.jneurophys_pubmed_only
            jneurophys_papers = fetch_all_jneurophys_papers(days=args.days, use_both_sources=use_both)

        if fetch_all or args.jneurosci_only:
            jneurosci_papers = fetch_all_jneurosci_papers(
                days=args.days,
                include_journal_club=args.include_journal_club
            )

        if fetch_all or args.jcogn_only:
            jcogn_papers = fetch_all_jcogn_papers(days=args.days)

        if fetch_all or args.jvis_only:
            jvis_papers = fetch_all_jvis_papers(days=args.days)

        if fetch_all or args.pnas_only:
            pnas_papers = fetch_all_pnas_papers(days=args.days)

        if fetch_all or args.natcomm_only:
            natcomm_papers = fetch_all_natcomm_papers(days=args.days)

        if fetch_all or args.brain_only:
            brain_papers = fetch_all_brain_papers(days=args.days)

        if fetch_all or args.sciadv_only:
            headless = args.headless.lower() != 'false'
            sciadv_papers = fetch_all_sciadv_papers(days=args.days, headless=headless)

        if fetch_all or args.elife_only:
            elife_papers = fetch_all_elife_papers(days=args.days)

        if args.no_merge:
            if args.arxiv_only and arxiv_papers:
                arxiv_filename = f"arxiv_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, arxiv_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in arxiv_papers:
                        f.write(paper)
                print(f"\nSaved arXiv papers to: {filepath}")

            if args.biorxiv_only and biorxiv_papers:
                biorxiv_filename = f"biorxiv_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, biorxiv_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in biorxiv_papers:
                        f.write(paper)
                print(f"\nSaved bioRxiv papers to: {filepath}")

            if args.nature_only and nature_papers:
                nature_filename = f"nature_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, nature_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in nature_papers:
                        f.write(paper)
                print(f"\nSaved Nature papers to: {filepath}")

            if args.science_only and science_papers:
                science_filename = f"science_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, science_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in science_papers:
                        f.write(paper)
                print(f"\nSaved Science papers to: {filepath}")

            if args.cell_only and cell_papers:
                cell_filename = f"cell_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, cell_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in cell_papers:
                        f.write(paper)
                print(f"\nSaved Cell Press papers to: {filepath}")

            if args.jneurophys_only and jneurophys_papers:
                jneurophys_filename = f"jneurophys_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jneurophys_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jneurophys_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Neurophysiology papers to: {filepath}")

            if args.jneurosci_only and jneurosci_papers:
                jneurosci_filename = f"jneurosci_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jneurosci_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jneurosci_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Neuroscience papers to: {filepath}")

            if args.jcogn_only and jcogn_papers:
                jcogn_filename = f"jcogn_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jcogn_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jcogn_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Cognitive Neuroscience papers to: {filepath}")

            if args.jvis_only and jvis_papers:
                jvis_filename = f"jvis_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, jvis_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in jvis_papers:
                        f.write(paper)
                print(f"\nSaved Journal of Vision papers to: {filepath}")

            if args.pnas_only and pnas_papers:
                pnas_filename = f"pnas_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, pnas_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in pnas_papers:
                        f.write(paper)
                print(f"\nSaved PNAS papers to: {filepath}")

            if args.natcomm_only and natcomm_papers:
                natcomm_filename = f"natcomm_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, natcomm_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in natcomm_papers:
                        f.write(paper)
                print(f"\nSaved Nature Communications papers to: {filepath}")

            if args.brain_only and brain_papers:
                brain_filename = f"brain_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, brain_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in brain_papers:
                        f.write(paper)
                print(f"\nSaved Brain papers to: {filepath}")

            if args.sciadv_only and sciadv_papers:
                sciadv_filename = f"sciadv_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, sciadv_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in sciadv_papers:
                        f.write(paper)
                print(f"\nSaved Science Advances papers to: {filepath}")

            if args.elife_only and elife_papers:
                elife_filename = f"elife_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
                filepath = os.path.join(args.output_dir, elife_filename)
                with jsonlines.open(filepath, 'w') as f:
                    for paper in elife_papers:
                        f.write(paper)
                print(f"\nSaved eLife papers to: {filepath}")

            print("\n[OK] Done!")

        else:
            if args.skip_dedup:
                merged_papers = []
                merged_papers.extend(arxiv_papers)
                merged_papers.extend(biorxiv_papers)
                merged_papers.extend(nature_papers)
                merged_papers.extend(science_papers)
                merged_papers.extend(cell_papers)
                merged_papers.extend(jneurophys_papers)
                merged_papers.extend(jneurosci_papers)
                merged_papers.extend(jcogn_papers)
                merged_papers.extend(jvis_papers)
                merged_papers.extend(pnas_papers)
                merged_papers.extend(natcomm_papers)
                merged_papers.extend(brain_papers)
                merged_papers.extend(sciadv_papers)
                merged_papers.extend(elife_papers)
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
                merged_papers = merge_papers(arxiv_papers, biorxiv_papers, nature_papers, science_papers,
                                         cell_papers, jneurophys_papers, jneurosci_papers, jcogn_papers,
                                         jvis_papers, pnas_papers, natcomm_papers, brain_papers,
                                         sciadv_papers, elife_papers)

            raw_filepath = save_merged_papers(merged_papers, args.output_dir)
            save_source_summary(arxiv_papers, biorxiv_papers, nature_papers, science_papers, cell_papers,
                               jneurophys_papers, jneurosci_papers, jcogn_papers, jvis_papers, pnas_papers,
                               natcomm_papers, brain_papers, sciadv_papers, elife_papers, args.output_dir)
            print_summary(arxiv_papers, biorxiv_papers, nature_papers, science_papers, cell_papers,
                         jneurophys_papers, jneurosci_papers, jcogn_papers, jvis_papers, pnas_papers,
                         natcomm_papers, brain_papers, sciadv_papers, elife_papers, merged_papers)

            if not args.no_auto_enrich:
                print("\n" + "=" * 80)
                print("STARTING AUTOMATIC AUTHOR ENRICHMENT")
                print("=" * 80)

                start_time = time.time()

                enriched_papers = enrich_papers_concurrent(merged_papers, max_workers=args.workers)

                ror_search = ROR_Search(threshold=args.ror_threshold)
                enriched_papers = normalize_affiliations_with_ror(enriched_papers, ror_search)

                enriched_filepath = save_enriched_papers(enriched_papers, args.output_dir)

                elapsed = time.time() - start_time

                print_enrichment_statistics(enriched_papers)

                print(f"\nTotal enrichment time: {elapsed:.1f}s "
                      f"({elapsed/len(enriched_papers):.1f}s per paper)")
                print(f"Final enriched output: {enriched_filepath}")

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
