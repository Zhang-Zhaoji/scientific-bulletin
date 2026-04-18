"""
测试缓存命中率

使用之前爬取的JSONL文件作为输入，测试SQLite缓存能够覆盖多少比例的作者查询。
"""

import jsonlines
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from enrich_authors import get_database, get_priority_authors


def test_cache_hit_rate(jsonl_path: str):
    """测试缓存命中率"""
    print("=" * 80)
    print(f"Testing cache hit rate using: {jsonl_path}")
    print("=" * 80)

    db = get_database()

    total_papers = 0
    total_priority_authors = 0
    cache_hits = 0
    cache_misses = 0
    hit_authors = []
    miss_authors = []

    with jsonlines.open(jsonl_path) as f:
        for paper in f:
            total_papers += 1
            authors = paper.get('authors', [])

            if not authors:
                continue

            priority_authors = get_priority_authors(authors)
            total_priority_authors += len(priority_authors)

            for idx, author_name in priority_authors:
                cached = db.get_author(author_name)

                if cached:
                    cache_hits += 1
                    hit_authors.append(author_name)
                else:
                    cache_misses += 1
                    miss_authors.append(author_name)

            if total_papers % 50 == 0:
                print(f"  Processed {total_papers} papers, {total_priority_authors} priority authors...")

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total papers: {total_papers}")
    print(f"Total priority authors (first 3 + last 3): {total_priority_authors}")
    print(f"Cache hits: {cache_hits}")
    print(f"Cache misses: {cache_misses}")
    print(f"\nCache hit rate: {cache_hits / total_priority_authors * 100:.2f}%")
    print(f"Cache miss rate: {cache_misses / total_priority_authors * 100:.2f}%")

    print("\n" + "=" * 80)
    print("SAMPLE CACHED AUTHORS (first 10)")
    print("=" * 80)
    for name in hit_authors[:10]:
        author = db.get_author(name)
        print(f"  - {name}: h_index={author.get('h_index')}, citations={author.get('citations')}")

    print("\n" + "=" * 80)
    print("SAMPLE MISSED AUTHORS (first 10)")
    print("=" * 80)
    for name in miss_authors[:10]:
        print(f"  - {name}")

    unique_hit_authors = set(hit_authors)
    unique_miss_authors = set(miss_authors)

    print("\n" + "=" * 80)
    print("UNIQUE AUTHOR STATS")
    print("=" * 80)
    print(f"Unique cached authors: {len(unique_hit_authors)}")
    print(f"Unique missed authors: {len(unique_miss_authors)}")

    return {
        'total_papers': total_papers,
        'total_priority_authors': total_priority_authors,
        'cache_hits': cache_hits,
        'cache_misses': cache_misses,
        'hit_rate': cache_hits / total_priority_authors * 100,
        'unique_hit_authors': len(unique_hit_authors),
        'unique_miss_authors': len(unique_miss_authors)
    }


def main():
    if len(sys.argv) > 1:
        jsonl_path = sys.argv[1]
    else:
        jsonl_path = 'getfiles/all_papers_2026-04-18_enriched.jsonl'

    if not os.path.exists(jsonl_path):
        print(f"Error: File not found: {jsonl_path}")
        sys.exit(1)

    results = test_cache_hit_rate(jsonl_path)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Cache can reduce API calls by approximately {results['hit_rate']:.1f}%")
    print(f"This means for every 100 author queries, {results['hit_rate']:.0f} will use cached data")


if __name__ == '__main__':
    main()