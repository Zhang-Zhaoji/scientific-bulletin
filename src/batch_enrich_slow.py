"""
Slow Batch Enrichment - Conservative Rate Limiting

适用于大批量论文的安全处理版本
- PubMed: 3 requests/sec (无key) 或 10/sec (有key)
- OpenAlex: 10 requests/sec
"""

import argparse
import jsonlines
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enrich_authors import enrich_papers_concurrent, get_db


def batch_enrich_slow(input_files: list, max_workers: int = 3, batch_size: int = 50, rest_time: float = 10.0):
    """
    慢速批量处理，避免触发API限制
    
    Args:
        input_files: 输入文件列表
        max_workers: 最大并发数（建议3-5）
        batch_size: 每批处理的论文数（默认50）
        rest_time: 每批之间的休息时间（秒）
    """
    
    total_papers = 0
    total_time = 0
    
    for input_file in input_files:
        print(f"\n{'='*80}")
        print(f"Processing: {input_file}")
        print(f"{'='*80}")
        
        if not os.path.exists(input_file):
            print(f"[SKIP] File not found: {input_file}")
            continue
        
        # 确定输出文件名
        base, ext = os.path.splitext(input_file)
        if '_enriched' in base:
            output_file = input_file
        else:
            output_file = f"{base}_enriched{ext}"
        
        # 加载论文
        with jsonlines.open(input_file) as f:
            papers = list(f)
        
        total = len(papers)
        if total == 0:
            print(f"[SKIP] No papers in {input_file}")
            continue
        
        print(f"Total papers: {total}")
        print(f"Output: {output_file}")
        print(f"Settings: workers={max_workers}, batch_size={batch_size}, rest={rest_time}s")
        
        # 分批处理
        all_enriched = []
        batches = list(range(0, total, batch_size))
        
        for i, start in enumerate(batches):
            end = min(start + batch_size, total)
            batch = papers[start:end]
            
            print(f"\n  [Batch {i+1}/{len(batches)}] Papers {start+1}-{end}/{total}")
            print(f"  {'-'*60}")
            
            batch_start = time.time()
            
            # 处理本批
            try:
                enriched_batch = enrich_papers_concurrent(batch, max_workers=max_workers)
                all_enriched.extend(enriched_batch)
                
                batch_time = time.time() - batch_start
                print(f"  [Batch {i+1}] Completed in {batch_time:.1f}s")
                
                # 如果不是最后一批，休息
                if i < len(batches) - 1:
                    print(f"  [Resting {rest_time}s to avoid rate limits...]")
                    time.sleep(rest_time)
                    
            except Exception as e:
                print(f"  [ERROR] Batch {i+1} failed: {e}")
                # 保存失败的批次标记
                for p in batch:
                    p['author_enrichment_status'] = 'error'
                    p['enrichment_error'] = str(e)
                    all_enriched.append(p)
        
        # 保存结果
        print(f"\n  Saving {len(all_enriched)} papers to {output_file}...")
        with jsonlines.open(output_file, 'w') as f:
            for p in all_enriched:
                f.write(p)
        
        # 统计
        success = sum(1 for p in all_enriched if p.get('author_enrichment_status') == 'enriched')
        seniors = sum(p.get('senior_author_count', 0) for p in all_enriched)
        
        print(f"  [OK] Saved! Success: {success}/{total}, Senior authors: {seniors}")
        
        total_papers += total
        total_time += time.time()  # 粗略估计
        
        # 文件之间也休息
        if input_file != input_files[-1]:
            print(f"\n{'='*80}")
            print(f"[Resting 30s before next file...]")
            time.sleep(30)
    
    # 最终数据库保存
    db = get_db()
    db.save_databases()
    
    print(f"\n{'='*80}")
    print(f"ALL DONE! Total papers processed: {total_papers}")
    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='Slow batch enrichment with conservative rate limiting'
    )
    parser.add_argument('files', nargs='+', help='Input JSONL files')
    parser.add_argument('-w', '--workers', type=int, default=3, 
                       help='Concurrent workers (default: 3, recommend 3-5)')
    parser.add_argument('-b', '--batch-size', type=int, default=50,
                       help='Papers per batch (default: 50)')
    parser.add_argument('-r', '--rest', type=float, default=10.0,
                       help='Rest time between batches in seconds (default: 10)')
    
    args = parser.parse_args()
    
    batch_enrich_slow(args.files, args.workers, args.batch_size, args.rest)


if __name__ == '__main__':
    main()
