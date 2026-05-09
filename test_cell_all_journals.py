"""
Test ALL Cell Press journals with Scrapling Beta
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from crawler_cell_beta import fetch_cell_papers, CELL_JOURNALS

print("=" * 80)
print("Testing ALL Cell Press journals with Scrapling Beta")
print("Available:", list(CELL_JOURNALS.keys()))
print("=" * 80)

for key in CELL_JOURNALS:
    print(f"\n--- Testing journal: {key} ---")
    try:
        articles = fetch_cell_papers(journals=[key], days=7, enrich=False, headless=True)
        print(f"[OK] {key}: {len(articles)} articles")
        if articles:
            for a in articles[:2]:
                print(f"  - {a['title'][:60]}... ({a['date']})")
    except Exception as e:
        print(f"[ERROR] {key}: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("All tests completed")
print("=" * 80)
