#!/usr/bin/env python
"""测试Nature爬虫的日期处理"""
import sys
sys.path.insert(0, 'src')

from crawler_nature import extract_text, get_start_date, process_nature_article_infos

print("=== 测试 get_start_date ===")
start_date_7 = get_start_date(7)
start_date_30 = get_start_date(30)
print(f"Default (7 days): {start_date_7}")
print(f"30 days: {start_date_30}")

print("\n=== 测试 extract_text (7 days, max 2 pages) ===")
url = 'https://www.nature.com/nature/research-articles'
try:
    articles = extract_text(url, days_back=7, max_pages=2)
    print(f"\nTotal articles found: {len(articles)}")
    for a in articles[:5]:
        print(f"  - {a['date']}: {a['title'][:50]}...")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
