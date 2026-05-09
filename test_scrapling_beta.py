"""
Test script for Scrapling-based beta crawlers (crawler_science_beta & crawler_cell_beta)
"""
import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

print("=" * 80)
print("Testing Scrapling Beta Crawlers")
print("=" * 80)

# --- Test 1: Science Beta ---
print("\n" + "=" * 80)
print("TEST 1: crawler_science_beta")
print("=" * 80)

try:
    from crawler_science_beta import fetch_science_list
    print("\n[OK] Import successful")

    print("\nFetching Science articles (last 7 days)...")
    science_articles = fetch_science_list(headless=True, days=7)

    print(f"\n[RESULT] Fetched {len(science_articles)} articles")

    if science_articles:
        print("\nSample articles:")
        for i, article in enumerate(science_articles[:3], 1):
            print(f"  [{i}] {article.get('title', 'N/A')[:70]}...")
            print(f"      Date: {article.get('date', 'N/A')}")
            print(f"      Type: {article.get('type', 'N/A')}")
            print(f"      DOI: {article.get('doi', 'N/A')[:30]}...")
            print(f"      URL: {article.get('url', 'N/A')[:60]}...")
            print()
    else:
        print("[WARN] No articles found")

except Exception as e:
    print(f"[ERROR] Science beta test failed: {e}")
    import traceback
    traceback.print_exc()

# --- Test 2: Cell Beta ---
print("\n" + "=" * 80)
print("TEST 2: crawler_cell_beta")
print("=" * 80)

try:
    from crawler_cell_beta import fetch_cell_papers
    print("\n[OK] Import successful")

    print("\nFetching Cell Press articles (Neuron, last 7 days, no enrich)...")
    cell_articles = fetch_cell_papers(
        journals=['neuron'],
        days=7,
        enrich=False,
        headless=True
    )

    print(f"\n[RESULT] Fetched {len(cell_articles)} articles")

    if cell_articles:
        print("\nSample articles:")
        for i, article in enumerate(cell_articles[:3], 1):
            print(f"  [{i}] {article.get('title', 'N/A')[:70]}...")
            print(f"      Date: {article.get('date', 'N/A')}")
            print(f"      Source: {article.get('source', 'N/A')}")
            print(f"      URL: {article.get('url', 'N/A')[:60]}...")
            print()
    else:
        print("[WARN] No articles found")

except Exception as e:
    print(f"[ERROR] Cell beta test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("Test completed")
print("=" * 80)
