"""
Crawler for Europe PMC (PubMed Central Europe)
API Docs: https://europepmc.org/RestfulWebService

Europe PMC provides free access to biomedical literature, including:
- PubMed abstracts
- PMC full-text articles (open access)
- Author manuscripts
- Patent abstracts

This crawler can search by:
- Title
- DOI
- PubMed ID
- PMC ID
"""
import requests
import datetime
import time
from typing import List, Dict, Optional, Tuple
import jsonlines

# Europe PMC API base URL
EUROPEPMC_API_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def search_by_doi(doi: str) -> Optional[Dict]:
    """
    Search for a paper by DOI.
    
    Args:
        doi: DOI string (e.g., "10.1126/science.aeb6999")
    
    Returns:
        Paper dictionary or None if not found
    """
    # Remove 'doi:' prefix if present
    doi = doi.replace('doi:', '').replace('DOI:', '').strip()
    
    url = f"{EUROPEPMC_API_URL}/search"
    params = {
        "query": f"DOI:{doi}",
        "resultType": "core",  # Returns full metadata including abstract
        "format": "json",
        "pageSize": 1
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        result_list = data.get('resultList', {}).get('result', [])
        if not result_list:
            print(f"[INFO] No results found for DOI: {doi}")
            return None
        
        return parse_europepmc_result(result_list[0])
    
    except requests.RequestException as e:
        print(f"[ERROR] Failed to search by DOI: {e}")
        return None


def search_by_title(title: str, fuzzy: bool = True) -> Optional[Dict]:
    """
    Search for a paper by title.
    
    Args:
        title: Paper title
        fuzzy: If True, use fuzzy matching (more tolerant of small differences)
    
    Returns:
        Paper dictionary or None if not found
    """
    url = f"{EUROPEPMC_API_URL}/search"
    
    # Clean title for search
    search_title = title.strip()
    if len(search_title) > 200:
        # Truncate very long titles
        search_title = search_title[:200]
    
    # Quote the title for exact phrase search
    query = f'TITLE:"{search_title}"'
    
    params = {
        "query": query,
        "resultType": "core",
        "format": "json",
        "pageSize": 5  # Get a few results to find best match
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        result_list = data.get('resultList', {}).get('result', [])
        if not result_list:
            if fuzzy:
                # Try without quotes for broader search
                return search_by_title_fuzzy(title)
            return None
        
        # Find best match
        best_match = None
        best_score = 0
        
        for result in result_list:
            result_title = result.get('title', '')
            # Calculate simple similarity score
            score = calculate_title_similarity(title, result_title)
            if score > best_score and score > 0.8:  # Threshold for match
                best_score = score
                best_match = result
        
        if best_match:
            return parse_europepmc_result(best_match)
        
        # If no good match but we have results, return the first one
        if result_list and fuzzy:
            return parse_europepmc_result(result_list[0])
        
        return None
    
    except requests.RequestException as e:
        print(f"[ERROR] Failed to search by title: {e}")
        return None


def search_by_title_fuzzy(title: str) -> Optional[Dict]:
    """
    Fuzzy title search (broader matching).
    """
    url = f"{EUROPEPMC_API_URL}/search"
    
    # Extract key words (remove common stop words)
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    words = [w for w in title.strip().split() if w.lower() not in stop_words][:10]  # Use first 10 keywords
    
    if not words:
        return None
    
    query = ' AND '.join(words)
    
    params = {
        "query": query,
        "resultType": "core",
        "format": "json",
        "pageSize": 5
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        result_list = data.get('resultList', {}).get('result', [])
        if not result_list:
            return None
        
        return parse_europepmc_result(result_list[0])
    
    except requests.RequestException as e:
        print(f"[ERROR] Failed fuzzy search: {e}")
        return None


def calculate_title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two titles (0-1 scale).
    """
    # Normalize titles
    t1 = title1.lower().strip()
    t2 = title2.lower().strip()
    
    # Remove punctuation
    for char in '.,;:?!"\'()-[]{}':
        t1 = t1.replace(char, ' ')
        t2 = t2.replace(char, ' ')
    
    # Split into words
    words1 = set(t1.split())
    words2 = set(t2.split())
    
    if not words1 or not words2:
        return 0.0
    
    # Jaccard similarity
    intersection = words1 & words2
    union = words1 | words2
    
    return len(intersection) / len(union)


def parse_europepmc_result(result: Dict) -> Optional[Dict]:
    """
    Parse a Europe PMC search result into our standard format.
    """
    try:
        # Extract title
        if not isinstance(result, dict):
            print(f"[WARN] Result is not a dict: {type(result)}")
            return None
            
        title = result.get('title', 'No title').strip()
        
        # Extract authors
        authors = []
        author_list = result.get('authorList', {}).get('author', [])
        if isinstance(author_list, dict):
            # Single author
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
        pub_date = result.get('firstPublicationDate', '')
        if not pub_date:
            pub_date = result.get('pubYear', '')
        
        # Format date
        date_formatted = format_date(pub_date)
        
        # Extract abstract
        abstract = result.get('abstractText', '')
        if not abstract:
            abstract = result.get('abstract', '')
        
        # Clean abstract
        if abstract:
            abstract = abstract.strip()
            # Remove "Abstract" prefix if present
            if abstract.lower().startswith('abstract'):
                abstract = abstract[8:].strip()
        
        # Extract DOI
        doi = result.get('doi', '')
        
        # Extract PMID and PMCID
        pmid = result.get('pmid', '')
        pmcid = result.get('pmcid', '')
        
        # Construct URLs
        full_text_urls = result.get('fullTextUrlList', {})
        europepmc_url = ''
        if full_text_urls and 'fullTextId' in full_text_urls:
            ft_ids = full_text_urls['fullTextId']
            if isinstance(ft_ids, list) and len(ft_ids) > 0:
                europepmc_url = f"https://europepmc.org/article/{ft_ids[0]}"
        
        if not europepmc_url and pmcid:
            europepmc_url = f"https://europepmc.org/article/PMC/{pmcid.replace('PMC', '')}"
        
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ''
        doi_url = f"https://doi.org/{doi}" if doi else ''
        
        # Extract journal info
        journal = result.get('journalTitle', '')
        journal_volume = result.get('journalVolume', '')
        journal_issue = result.get('issue', '')
        page_info = result.get('pageInfo', '')
        
        # Is it open access?
        is_open_access = result.get('isOpenAccess', 'N') == 'Y'
        
        # Publication type
        pub_type = result.get('pubType', '')
        
        return {
            'type': 'Article',
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
            'is_open_access': is_open_access,
            'pub_type': pub_type,
            'pubmed_url': pubmed_url,
            'doi_url': doi_url,
            'source': 'Europe PMC'
        }
    
    except Exception as e:
        print(f"[WARN] Failed to parse Europe PMC result: {e}")
        return None


def format_date(date_str: str) -> str:
    """
    Format various date formats to 'DD MMM YYYY'.
    """
    if not date_str:
        return ''
    
    date_str = str(date_str).strip()
    
    # Try different formats
    formats = [
        '%Y-%m-%d',      # 2024-01-15
        '%Y-%m',         # 2024-01
        '%Y',            # 2024
        '%d-%m-%Y',      # 15-01-2024
        '%d/%m/%Y',      # 15/01/2024
        '%b %Y',         # Jan 2024
        '%B %Y',         # January 2024
    ]
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            return dt.strftime('%d %b %Y')
        except ValueError:
            continue
    
    # If no format matches, return original
    return date_str


def fetch_article_by_identifier(identifier: str, id_type: str = 'auto') -> Optional[Dict]:
    """
    Fetch article by various identifiers.
    
    Args:
        identifier: DOI, PMID, PMCID, or title
        id_type: 'doi', 'pmid', 'pmcid', 'title', or 'auto' (detect automatically)
    
    Returns:
        Paper dictionary or None
    """
    if id_type == 'auto':
        id_type = detect_identifier_type(identifier)
    
    if id_type == 'doi':
        return search_by_doi(identifier)
    elif id_type == 'pmid':
        return search_by_pmid(identifier)
    elif id_type == 'pmcid':
        return search_by_pmcid(identifier)
    elif id_type == 'title':
        return search_by_title(identifier)
    else:
        print(f"[WARN] Unknown identifier type for: {identifier}")
        return None


def detect_identifier_type(identifier: str) -> str:
    """
    Auto-detect identifier type.
    """
    identifier = identifier.strip()
    
    # DOI pattern
    if identifier.startswith('10.'):
        return 'doi'
    if 'doi' in identifier.lower():
        return 'doi'
    
    # PMCID pattern (PMC123456)
    if identifier.upper().startswith('PMC'):
        return 'pmcid'
    
    # PMID pattern (all digits, typically 8 digits)
    if identifier.isdigit() and len(identifier) >= 6:
        return 'pmid'
    
    # Assume it's a title
    return 'title'


def search_by_pmid(pmid: str) -> Optional[Dict]:
    """Search by PubMed ID."""
    url = f"{EUROPEPMC_API_URL}/search"
    params = {
        "query": f"EXT_ID:{pmid}",
        "resultType": "core",
        "format": "json",
        "pageSize": 1
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        result_list = data.get('resultList', {}).get('result', [])
        if result_list:
            return parse_europepmc_result(result_list[0])
        return None
    
    except requests.RequestException as e:
        print(f"[ERROR] Failed to search by PMID: {e}")
        return None


def search_by_pmcid(pmcid: str) -> Optional[Dict]:
    """Search by PMC ID."""
    # Ensure PMC prefix
    if not pmcid.upper().startswith('PMC'):
        pmcid = f"PMC{pmcid}"
    
    url = f"{EUROPEPMC_API_URL}/search"
    params = {
        "query": f"PMCID:{pmcid}",
        "resultType": "core",
        "format": "json",
        "pageSize": 1
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        result_list = data.get('resultList', {}).get('result', [])
        if result_list:
            return parse_europepmc_result(result_list[0])
        return None
    
    except requests.RequestException as e:
        print(f"[ERROR] Failed to search by PMCID: {e}")
        return None


def batch_search(identifiers: List[str], delay: float = 0.5) -> List[Dict]:
    """
    Search for multiple articles by various identifiers.
    
    Args:
        identifiers: List of DOIs, PMIDs, or titles
        delay: Delay between requests (be nice to the API)
    
    Returns:
        List of found paper dictionaries
    """
    results = []
    
    for i, identifier in enumerate(identifiers):
        print(f"[{i+1}/{len(identifiers)}] Searching: {identifier[:80]}...")
        
        paper = fetch_article_by_identifier(identifier)
        if paper:
            results.append(paper)
            print(f"  -> Found: {paper['title'][:60]}...")
        else:
            print(f"  -> Not found")
        
        time.sleep(delay)
    
    return results


def save_papers(papers: List[Dict], filepath: Optional[str] = None) -> str:
    """Save papers to a JSONL file."""
    if filepath is None:
        filepath = f"getfiles/europepmc-{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"
    
    with jsonlines.open(filepath, 'w') as f:
        for paper in papers:
            f.write(paper)
    
    return filepath


# ============== Test Functions ==============

def test_with_sample():
    """
    Test the crawler with the provided sample from testSample.txt.
    Also tests with known working examples to verify the API is functional.
    """
    print("=" * 80)
    print("Testing Europe PMC Crawler with Sample")
    print("=" * 80)
    
    # First, test with a known working DOI to verify API connectivity
    print("\n[API Connectivity Test]")
    print("Testing with a known article to verify API is accessible...")
    
    # This is a well-known open access article that should be in Europe PMC
    test_doi = "10.1038/s41586-021-03819-2"  # A Nature article about microglia
    
    test_paper = search_by_doi(test_doi)
    if test_paper:
        print(f"[OK] API is working! Found test article: {test_paper['title'][:60]}...")
        print(f"    PMID: {test_paper['pmid']}, Open Access: {test_paper['is_open_access']}")
    else:
        print("[WARN] API connectivity test failed - Europe PMC may be down or network issue")
    
    # Read test sample
    try:
        with open('testSample.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("\n[ERROR] testSample.txt not found!")
        print("Testing with known examples instead...")
        return test_with_known_examples()
    
    # Parse the sample
    line1 = lines[0].strip() if len(lines) > 0 else ""
    line2 = lines[1].strip() if len(lines) > 1 else ""
    line3 = lines[2].strip() if len(lines) > 2 else ""
    
    # Extract title from line 1
    if ',' in line1:
        parts = line1.split(',', 1)
        authors = parts[0].strip()
        title = parts[1].replace('.', '').strip()
    else:
        authors = ""
        title = line1
    
    # Extract DOI from line 3
    doi = line3.replace('DOI:', '').replace('doi:', '').strip()
    
    journal = line2.split(',')[0] if ',' in line2 else line2
    
    print(f"\n[Sample Info from testSample.txt]")
    print(f"Title: {title}")
    print(f"Authors: {authors}")
    print(f"Journal: {journal}")
    print(f"DOI: {doi}")
    
    # Note: This is a very recent Science article (2026/2025)
    # Europe PMC may not have indexed it yet
    print("\n[NOTE] This is a very recent article from Science.")
    print("Europe PMC may take several days/weeks to index new articles.")
    
    # Test 1: Search by DOI
    print("\n" + "-" * 80)
    print("Test 1: Search by DOI")
    print("-" * 80)
    
    paper_by_doi = search_by_doi(doi)
    if paper_by_doi:
        print(f"[OK] Found by DOI!")
        print(f"  Title: {paper_by_doi['title'][:80]}...")
        print(f"  Abstract length: {len(paper_by_doi['abstract'])} chars")
        print(f"  PMID: {paper_by_doi['pmid']}")
        print(f"  PMCID: {paper_by_doi['pmcid']}")
        print(f"  Open Access: {paper_by_doi['is_open_access']}")
    else:
        print("[NOT FOUND] Not found by DOI")
        print("  This is expected for very recent articles not yet indexed in Europe PMC.")
    
    # Test 2: Search by Title
    print("\n" + "-" * 80)
    print("Test 2: Search by Title")
    print("-" * 80)
    
    paper_by_title = search_by_title(title)
    if paper_by_title:
        print(f"[OK] Found by Title!")
        print(f"  Title: {paper_by_title['title'][:80]}...")
        print(f"  DOI match: {paper_by_title['doi'] == doi}")
    else:
        print("[NOT FOUND] Not found by Title")
    
    # Test 3: Auto-detect identifier
    print("\n" + "-" * 80)
    print("Test 3: Auto-detect Identifier")
    print("-" * 80)
    
    paper_auto = fetch_article_by_identifier(doi)
    if paper_auto:
        print(f"[OK] Auto-detect worked!")
        print(f"  Detected type: {detect_identifier_type(doi)}")
    else:
        print("[NOT FOUND] Auto-detect failed")
    
    # Save results
    results = [p for p in [paper_by_doi, paper_by_title, paper_auto, test_paper] if p]
    if results:
        # Remove duplicates
        seen_dois = set()
        unique_results = []
        for p in results:
            if p['doi'] not in seen_dois:
                seen_dois.add(p['doi'])
                unique_results.append(p)
        
        filepath = save_papers(unique_results, "getfiles/europepmc_test_sample.jsonl")
        print(f"\n[SAVED] Saved {len(unique_results)} unique result(s) to: {filepath}")
    
    return results


def test_batch_search():
    """
    Test batch search with multiple identifiers.
    """
    print("\n" + "=" * 80)
    print("Testing Batch Search")
    print("=" * 80)
    
    test_cases = [
        "10.1126/science.aeb6999",  # Our sample DOI
        "10.1038/s41586-024-07901-7",  # Nature paper
        "Microglia Rank signaling regulates GnRH neuronal function",  # Partial title
    ]
    
    results = batch_search(test_cases, delay=1.0)
    
    print(f"\nFound {len(results)}/{len(test_cases)} papers")
    
    if results:
        filepath = save_papers(results, "getfiles/europepmc_test_batch.jsonl")
        print(f"Saved to: {filepath}")
    
    return results


def test_with_known_examples():
    """
    Test with known working examples to demonstrate functionality.
    """
    print("\n" + "=" * 80)
    print("Testing with Known Working Examples")
    print("=" * 80)
    
    test_cases = [
        {
            "desc": "Nature Neuroscience article (Open Access)",
            "doi": "10.1038/s41593-020-00744-9",
            "title": None
        },
        {
            "desc": "Science article via DOI",
            "doi": "10.1126/science.aay5193",
            "title": None
        },
        {
            "desc": "Search by title",
            "doi": None,
            "title": "Single-cell transcriptomic analysis of Alzheimer's disease"
        }
    ]
    
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n[{i}] {case['desc']}")
        print("-" * 40)
        
        if case['doi']:
            print(f"Searching by DOI: {case['doi']}")
            paper = search_by_doi(case['doi'])
        else:
            print(f"Searching by Title: {case['title'][:50]}...")
            paper = search_by_title(case['title'])
        
        if paper:
            print(f"[OK] Found!")
            print(f"  Title: {paper['title'][:70]}...")
            print(f"  Journal: {paper['journal']}")
            print(f"  Date: {paper['date']}")
            print(f"  PMID: {paper['pmid']}")
            print(f"  Abstract: {len(paper['abstract'])} chars")
            results.append(paper)
        else:
            print("[NOT FOUND]")
        
        time.sleep(1)  # Be nice to the API
    
    if results:
        filepath = save_papers(results, "getfiles/europepmc_known_examples.jsonl")
        print(f"\n[SAVED] Saved {len(results)} result(s) to: {filepath}")
    
    return results


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--batch':
        test_batch_search()
    elif len(sys.argv) > 1 and sys.argv[1] == '--known':
        test_with_known_examples()
    else:
        # Run sample test but also add known examples
        results = test_with_sample()
        if not results or len(results) <= 1:  # Only test article was found
            print("\n\nRunning additional tests with known examples...")
            test_with_known_examples()
