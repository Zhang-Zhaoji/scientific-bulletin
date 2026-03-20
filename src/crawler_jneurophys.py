"""
Crawler for Journal of Neurophysiology

Uses both PubMed API (faster updates) and Europe PMC (supplementary) to get 
recent articles. Automatically deduplicates based on PMID.
"""

import datetime
import time
from typing import List, Dict, Optional, Set
import jsonlines

# Import from generic PubMed crawler
from crawler_pubmed import (
    fetch_articles_by_journal as fetch_from_pubmed,
    search_pubmed,
    fetch_article_summaries,
    fetch_article_abstracts,
    DEFAULT_DELAY
)

# Journal name in PubMed/Europe PMC
PUBMED_JOURNAL_NAME = "Journal of Neurophysiology"
EUROPEPMC_JOURNAL_NAME = "Journal of Neurophysiology"

# Default: look back 7 days
DEFAULT_DAYS_BACK = 7


def fetch_from_europepmc(days: int = DEFAULT_DAYS_BACK, 
                         max_results: int = 100,
                         delay: float = 0.5) -> List[Dict]:
    """
    Fetch articles from Journal of Neurophysiology using Europe PMC API.
    
    Args:
        days: Number of days to look back
        max_results: Maximum number of results to fetch
        delay: Delay between API requests in seconds
        
    Returns:
        List of paper dictionaries
    """
    from crawler_europepmc import EUROPEPMC_API_URL
    
    print("Querying Europe PMC...")
    
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days*3)  # Extended range
    
    query = f'JOURNAL:"{EUROPEPMC_JOURNAL_NAME}" AND FIRST_PDATE:[{start_date.strftime("%Y-%m-%d")} TO {end_date.strftime("%Y-%m-%d")}]'
    
    all_papers = []
    page_size = 25
    cursor_mark = '*'
    total_found = 0
    
    while len(all_papers) < max_results:
        url = f"{EUROPEPMC_API_URL}/search"
        params = {
            "query": query,
            "resultType": "core",
            "format": "json",
            "pageSize": min(page_size, max_results - len(all_papers)),
            "cursorMark": cursor_mark,
            "sort": "P_PDATE_D desc"
        }
        
        try:
            import requests
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if total_found == 0:
                total_found = data.get('hitCount', 0)
            
            result_list = data.get('resultList', {}).get('result', [])
            if not result_list:
                break
            
            for result in result_list:
                # Only include formally published articles
                if result.get('publicationStatus') not in ('ppublish', 'epublish'):
                    continue
                
                # Check if within date range using print date
                journal_info = result.get('journalInfo', {})
                print_date = journal_info.get('printPublicationDate', '')
                if print_date:
                    try:
                        article_date = datetime.datetime.strptime(print_date, '%Y-%m-%d')
                        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
                        if article_date < cutoff_date:
                            continue
                    except ValueError:
                        pass
                
                paper = parse_europepmc_result(result)
                if paper:
                    all_papers.append(paper)
                
                if len(all_papers) >= max_results:
                    break
            
            next_cursor = data.get('nextCursorMark', '')
            if not next_cursor or next_cursor == cursor_mark:
                break
            cursor_mark = next_cursor
            
            time.sleep(delay)
            
        except Exception as e:
            print(f"[ERROR] Europe PMC API request failed: {e}")
            break
    
    return all_papers


def parse_europepmc_result(result: Dict) -> Optional[Dict]:
    """Parse a Europe PMC result into our standard format."""
    try:
        if not isinstance(result, dict):
            return None
        
        title = result.get('title', '').strip()
        if not title:
            return None
        
        # Extract authors
        authors = []
        author_list = result.get('authorList', {}).get('author', [])
        if isinstance(author_list, dict):
            author_list = [author_list]
        for author in author_list:
            if isinstance(author, dict):
                full_name = author.get('fullName', '')
                if not full_name:
                    first_name = author.get('firstName', '')
                    last_name = author.get('lastName', '')
                    full_name = f"{first_name} {last_name}".strip()
                if full_name:
                    authors.append(full_name)
        
        # Extract date
        journal_info = result.get('journalInfo', {})
        pub_date = journal_info.get('printPublicationDate', '')
        if not pub_date:
            pub_date = result.get('firstPublicationDate', '')
        if not pub_date:
            pub_date = result.get('pubYear', '')
        
        date_formatted = format_date(pub_date)
        
        # Extract abstract
        abstract = result.get('abstractText', '')
        if abstract:
            abstract = abstract.strip()
            if abstract.lower().startswith('abstract'):
                abstract = abstract[8:].strip()
        
        # Extract identifiers
        doi = result.get('doi', '')
        pmid = result.get('pmid', '')
        pmcid = result.get('pmcid', '')
        
        # Construct URLs
        doi_url = f"https://doi.org/{doi}" if doi else ''
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ''
        
        if pmcid:
            europepmc_url = f"https://europepmc.org/article/PMC/{pmcid.replace('PMC', '')}"
        elif pmid:
            europepmc_url = f"https://europepmc.org/article/MED/{pmid}"
        else:
            europepmc_url = doi_url
        
        # Extract journal info
        journal = journal_info.get('journal', {}).get('title', EUROPEPMC_JOURNAL_NAME)
        journal_volume = journal_info.get('volume', '')
        journal_issue = journal_info.get('issue', '')
        page_info = result.get('pageInfo', '')
        
        # Determine article type
        pub_type_list = result.get('pubTypeList', {}).get('pubType', [])
        if isinstance(pub_type_list, str):
            pub_type_list = [pub_type_list]
        
        title_lower = title.lower()
        is_review = 'review' in title_lower or any('review' in str(pt).lower() for pt in pub_type_list)
        
        if is_review:
            article_type = 'Review Article'
        else:
            article_type = 'Article'
        
        return {
            'type': article_type,
            'title': title,
            'authors': authors,
            'date': date_formatted,
            'url': europepmc_url or doi_url or pubmed_url,
            'abstract': abstract,
            'doi': doi,
            'pmid': pmid,
            'pmcid': pmcid,
            'journal': journal,
            'journal_volume': journal_volume,
            'journal_issue': journal_issue,
            'page_info': page_info,
            'doi_url': doi_url,
            'pubmed_url': pubmed_url,
            'source': 'Journal of Neurophysiology'
        }
    
    except Exception as e:
        print(f"[WARN] Failed to parse Europe PMC result: {e}")
        return None


def format_date(date_str: str) -> str:
    """Format various date formats to 'DD MMM YYYY'."""
    if not date_str:
        return ''
    
    date_str = str(date_str).strip()
    formats = [
        '%Y-%m-%d', '%Y-%m', '%Y',
        '%d-%m-%Y', '%d/%m/%Y',
        '%b %Y', '%B %Y',
    ]
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            return dt.strftime('%d %b %Y')
        except ValueError:
            continue
    
    return date_str


def merge_and_deduplicate(pubmed_papers: List[Dict], europepmc_papers: List[Dict]) -> List[Dict]:
    """
    Merge papers from PubMed and Europe PMC, removing duplicates based on PMID.
    PubMed data takes precedence when there are conflicts.
    
    Args:
        pubmed_papers: Papers from PubMed
        europepmc_papers: Papers from Europe PMC
        
    Returns:
        Merged list of unique papers
    """
    # Use PMID as the key for deduplication
    papers_by_pmid: Dict[str, Dict] = {}
    
    # Add PubMed papers first (they take precedence)
    for paper in pubmed_papers:
        pmid = paper.get('pmid')
        if pmid:
            papers_by_pmid[pmid] = paper
        else:
            # For papers without PMID, use title as key
            title_key = paper.get('title', '').lower().strip()
            if title_key:
                papers_by_pmid[f"title:{title_key}"] = paper
    
    # Add Europe PMC papers, skipping duplicates
    skipped = 0
    for paper in europepmc_papers:
        pmid = paper.get('pmid')
        if pmid and pmid in papers_by_pmid:
            # Duplicate - skip, but could merge abstract if PubMed version lacks it
            if not papers_by_pmid[pmid].get('abstract') and paper.get('abstract'):
                papers_by_pmid[pmid]['abstract'] = paper['abstract']
            skipped += 1
            continue
        
        # Check by title if no PMID
        title_key = paper.get('title', '').lower().strip()
        if title_key and f"title:{title_key}" in papers_by_pmid:
            skipped += 1
            continue
        
        if pmid:
            papers_by_pmid[pmid] = paper
        elif title_key:
            papers_by_pmid[f"title:{title_key}"] = paper
    
    if skipped > 0:
        print(f"  Skipped {skipped} duplicate(s) from Europe PMC")
    
    # Convert back to list and sort by date
    merged = list(papers_by_pmid.values())
    
    def parse_date_for_sort(paper):
        try:
            return datetime.datetime.strptime(paper.get('date', ''), '%d %b %Y')
        except ValueError:
            return datetime.datetime.min
    
    merged.sort(key=parse_date_for_sort, reverse=True)
    
    return merged


def fetch_jneurophys_papers(days: int = DEFAULT_DAYS_BACK,
                            max_results: int = 999,
                            fetch_abstracts: bool = True,
                            use_both_sources: bool = True,
                            delay: float = DEFAULT_DELAY) -> List[Dict]:
    """
    Fetch papers from Journal of Neurophysiology using PubMed (primary) and 
    optionally Europe PMC (supplementary).
    
    Args:
        days: Number of days to look back
        max_results: Maximum number of results to fetch
        fetch_abstracts: Whether to fetch full abstracts
        use_both_sources: Whether to also query Europe PMC for missing articles
        delay: Delay between API requests in seconds
        
    Returns:
        List of paper dictionaries
    """
    print("=" * 80)
    print(f"Fetching from Journal of Neurophysiology (last {days} days)...")
    if use_both_sources:
        print("Using PubMed (primary) + Europe PMC (supplementary)")
    else:
        print("Using PubMed only")
    print("=" * 80)
    
    # Step 1: Fetch from PubMed (faster updates)
    print("\n[1/2] Querying PubMed...")
    pubmed_papers = fetch_from_pubmed(
        journal_name=PUBMED_JOURNAL_NAME,
        days=days,
        max_results=max_results,
        fetch_abstracts=fetch_abstracts,
        exclude_types=['Erratum', 'Correction', 'Retraction'],
        delay=delay
    )
    
    print(f"  PubMed: {len(pubmed_papers)} articles")
    
    # Step 2: Optionally fetch from Europe PMC and merge
    if use_both_sources:
        print("\n[2/2] Querying Europe PMC for supplementary articles...")
        europepmc_papers = fetch_from_europepmc(
            days=days,
            max_results=max_results,
            delay=delay
        )
        print(f"  Europe PMC: {len(europepmc_papers)} articles")
        
        # Merge and deduplicate
        print("\nMerging and deduplicating...")
        all_papers = merge_and_deduplicate(pubmed_papers, europepmc_papers)
    else:
        all_papers = pubmed_papers
    
    # Update source field
    for paper in all_papers:
        paper['source'] = 'Journal of Neurophysiology'
    
    print(f"\nTotal Journal of Neurophysiology papers collected: {len(all_papers)}")
    return all_papers


def save_jneurophys_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
        filepath = f"getfiles/jneurophys_{timestamp}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    print(f"Saved {len(papers)} papers to: {filepath}")
    return filepath


# ============== Test Functions ==============

def test_fetch():
    """Test fetching papers from Journal of Neurophysiology."""
    print("\n" + "=" * 80)
    print("Testing Journal of Neurophysiology Crawler")
    print("=" * 80)
    
    # Test with last 7 days
    papers = fetch_jneurophys_papers(days=7, max_results=999, fetch_abstracts=True, use_both_sources=True)
    
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
            has_abstract = 'Yes' if paper.get('abstract') else 'No'
            print(f"    Has Abstract: {has_abstract}")
        
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
        save_jneurophys_papers(papers, "getfiles/jneurophys_test.jsonl")
    else:
        print("\nNo papers found.")
    
    return papers


if __name__ == '__main__':
    test_fetch()
