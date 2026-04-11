"""
Check what fields are available in PubMed for filtering.
We can query PubMed with subject restrictions.
"""
import requests
import json

# Test if we can search with MeSH/subject filtering
# Option 1: Use PubMed's subject filters
queries = [
    # Search PNAS with neuroscience MeSH term
    ('PNAS with Neuroscience MeSH', 
     'Proc Natl Acad Sci U S A[journal] AND (neuroscience[MeSH Terms] OR neuroscience[Title/Abstract]) AND 2026/04/01:2026/04/11[PDAT]'),
    
    # Search PNAS with biology-related terms
    ('PNAS with Biology terms',
     'Proc Natl Acad Sci U S A[journal] AND (biology[MeSH Terms] OR biological[Title/Abstract] OR cell[Title/Abstract] OR molecular[Title/Abstract]) AND 2026/04/01:2026/04/11[PDAT]'),
]

NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

for name, query in queries:
    print(f"\n{'='*80}")
    print(f"Query: {name}")
    print(f"Term: {query[:80]}...")
    
    url = f"{NCBI_BASE_URL}/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': query,
        'retmode': 'json',
        'retmax': 100
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        count = int(data.get('esearchresult', {}).get('count', 0))
        pmids = data.get('esearchresult', {}).get('idlist', [])
        print(f"Results: {count} articles")
        print(f"Sample PMIDs: {pmids[:5]}")
    except Exception as e:
        print(f"Error: {e}")

print("\n" + "="*80)
print("\nDirect PNAS search (no filter):")
query = 'Proc Natl Acad Sci U S A[journal] AND 2026/04/01:2026/04/11[PDAT]'
url = f"{NCBI_BASE_URL}/esearch.fcgi"
params = {
    'db': 'pubmed',
    'term': query,
    'retmode': 'json',
    'retmax': 100
}
try:
    response = requests.get(url, params=params, timeout=30)
    data = response.json()
    count = int(data.get('esearchresult', {}).get('count', 0))
    print(f"Results: {count} articles")
except Exception as e:
    print(f"Error: {e}")
