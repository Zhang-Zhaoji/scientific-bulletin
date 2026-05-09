"""
Debug script to inspect Scrapling Response object attributes
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

try:
    from scrapling.fetchers import StealthyFetcher
    print("[OK] Scrapling imported")

    url = 'https://www.science.org/journal/science/research?startPage=0&pageSize=100'
    print(f"\nFetching: {url}")
    page = StealthyFetcher.fetch(url, headless=True)

    print(f"\nType of page: {type(page)}")
    print(f"Type of page.text: {type(page.text)}")
    print(f"Length of page.text: {len(page.text)}")

    # Check other possible attributes
    attrs = ['text', 'body', 'content', 'html', 'source', 'raw', 'page_source']
    for attr in attrs:
        if hasattr(page, attr):
            val = getattr(page, attr)
            if isinstance(val, str):
                print(f"page.{attr}: len={len(val)}, type=str")
            elif isinstance(val, bytes):
                print(f"page.{attr}: len={len(val)}, type=bytes")
            else:
                print(f"page.{attr}: type={type(val)}")
        else:
            print(f"page.{attr}: NOT FOUND")

    # Try to see if it has find/find_all methods
    print(f"\nHas find_all: {hasattr(page, 'find_all')}")
    if hasattr(page, 'find_all'):
        cards = page.find_all('div', class_='card-header')
        print(f"Found {len(cards)} cards with page.find_all")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
