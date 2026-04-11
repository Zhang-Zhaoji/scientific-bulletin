"""
Batch Author Enrichment Script

批量处理论文文件，增强作者信息。
使用严格匹配策略，宁缺毋滥。

Usage:
    python batch_enrich_authors.py input.jsonl
    python batch_enrich_authors.py input.jsonl -o output.jsonl
    python batch_enrich_authors.py input.jsonl -l 100  # 只处理前100篇
"""

import jsonlines
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# 添加 src 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enrich_authors import enrich_paper_authors, get_database


def batch_enrich_papers(input_file: str, output_file: str = None, limit: int = None):
    """
    批量处理论文文件，增强作者信息
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径（默认在文件名后加 _enriched）
        limit: 限制处理数量（用于测试）
    """
    # 确定输出文件名
    if output_file is None:
        base, ext = os.path.splitext(input_file)
        # 如果已经是 enriched，不要重复加
        if '_enriched' in base:
            output_file = input_file
        else:
            output_file = f"{base}_enriched{ext}"
    
    print("=" * 80)
    print("Batch Author Enrichment (Strict Matching)")
    print("=" * 80)
    print(f"Input:  {input_file}")
    print(f"Output: {output_file}")
    if limit:
        print(f"Limit:  {limit} papers")
    print()
    
    # 检查输入文件
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return None
    
    # 加载论文
    print("Loading papers...")
    try:
        with jsonlines.open(input_file) as f:
            papers = list(f)
    except Exception as e:
        print(f"[ERROR] Failed to load input file: {e}")
        return None
    
    total = len(papers)
    if total == 0:
        print("[ERROR] No papers found in input file")
        return None
    
    if limit:
        papers = papers[:limit]
        print(f"Loaded {total} papers, processing first {limit}")
    else:
        print(f"Loaded {total} papers")
    
    # 批量处理
    enriched_papers = []
    stats = {
        'total': len(papers),
        'success': 0,
        'failed': 0,
        'with_senior': 0,
        'total_senior_authors': 0,
        'strict_skipped': 0,  # 严格模式跳过的
    }
    
    print("\nProcessing papers...")
    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}/{len(papers)}] {paper.get('title', 'Unknown')[:60]}...")
        
        try:
            enriched = enrich_paper_authors(
                paper,
                enable_affiliation=True,
                enable_impact=True,
                delay=0.3
            )
            enriched_papers.append(enriched)
            
            # 统计
            if enriched.get('author_enrichment_status') == 'enriched':
                stats['success'] += 1
            else:
                stats['failed'] += 1
            
            if enriched.get('has_senior_researcher'):
                stats['with_senior'] += 1
                stats['total_senior_authors'] += enriched.get('senior_author_count', 0)
            
            # 检查严格模式跳过的情况
            author_details = enriched.get('author_details', [])
            skipped = sum(1 for d in author_details if d.get('h_index') is None)
            if skipped > 0:
                stats['strict_skipped'] += skipped
            
            # 每10篇保存一次数据库（防止中断丢失数据）
            if i % 10 == 0:
                db = get_database()
                db.save_databases()
                print(f"    [Checkpoint] Saved database ({i} papers processed)")
                
        except Exception as e:
            print(f"\n[ERROR] Failed to process paper {i}: {e}")
            import traceback
            traceback.print_exc()
            # 保存原始数据，标记为失败
            paper['author_enrichment_status'] = 'error'
            paper['enrichment_error'] = str(e)
            enriched_papers.append(paper)
            stats['failed'] += 1
    
    # 最终保存数据库
    db = get_database()
    db.save_databases()
    
    # 保存结果
    print(f"\nSaving results to {output_file}...")
    try:
        with jsonlines.open(output_file, 'w') as f:
            for p in enriched_papers:
                f.write(p)
        print("[OK] Saved successfully")
    except Exception as e:
        print(f"[ERROR] Failed to save output: {e}")
        return None
    
    # 打印统计
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"Total processed:      {stats['total']}")
    print(f"Successful:           {stats['success']}")
    print(f"Failed:               {stats['failed']}")
    print(f"Papers with seniors:  {stats['with_senior']} ({stats['with_senior']/max(1,stats['total'])*100:.1f}%)")
    print(f"Total senior authors: {stats['total_senior_authors']}")
    print(f"Strict mode skipped:  {stats['strict_skipped']} (name/affiliation mismatch)")
    
    # 数据库统计
    print("\n" + "=" * 80)
    print("DATABASE STATISTICS")
    print("=" * 80)
    print(f"Authors in database:           {len(db.authors)}")
    print(f"Institutions in database:      {len(db.institutions)}")
    print(f"Senior researchers in database: {len(db.senior_researchers)}")
    
    # 显示大牛作者列表
    if db.senior_researchers:
        print(f"\nTop senior researchers found:")
        # 按 h-index 排序
        sorted_srs = sorted(
            db.senior_researchers.items(),
            key=lambda x: (x[1].get('h_index') or 0),
            reverse=True
        )
        for name, info in sorted_srs[:15]:  # 显示前15个
            h_idx = info.get('h_index', 'N/A') or 'N/A'
            cites = info.get('citations', 'N/A') or 'N/A'
            papers_count = info.get('paper_count', 0)
            print(f"  - {name:<30} h={h_idx:<4} cites={cites:<8} ({papers_count} papers)")
        
        if len(sorted_srs) > 15:
            print(f"  ... and {len(sorted_srs) - 15} more")
    
    print(f"\nOutput saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Batch enrich paper authors with strict matching',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_enrich_authors.py getfiles/all_papers_2026-04-11.jsonl
  python batch_enrich_authors.py input.jsonl -o output_enriched.jsonl
  python batch_enrich_authors.py input.jsonl -l 50  # Process only first 50
        """
    )
    
    parser.add_argument('input', help='Input JSONL file path')
    parser.add_argument('-o', '--output', help='Output JSONL file path (default: input_enriched.jsonl)')
    parser.add_argument('-l', '--limit', type=int, help='Limit number of papers to process')
    
    args = parser.parse_args()
    
    batch_enrich_papers(args.input, args.output, args.limit)


if __name__ == '__main__':
    main()
