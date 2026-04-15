"""
Robust Batch Enrichment - Handles API failures gracefully

特点:
- 自动降速: 遇到429错误时自动降低并发
- 断点续传: 支持中断后从上次位置继续
- 失败重试: 自动重试失败的作者查询
"""

import argparse
import jsonlines
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enrich_authors import enrich_papers_concurrent, get_db, AuthorDatabase


def batch_enrich_robust(input_files: list, max_workers: int = 5, batch_size: int = 50):
    """
    稳健批量处理，自动处理API限制
    """
    db = get_db()
    
    for input_file in input_files:
        print(f"\n{'='*80}")
        print(f"Processing: {os.path.basename(input_file)}")
        print(f"{'='*80}")
        
        if not os.path.exists(input_file):
            print(f"[SKIP] File not found: {input_file}")
            continue
        
        # 检查是否已有部分结果
        base, ext = os.path.splitext(input_file)
        output_file = f"{base}_enriched{ext}"
        checkpoint_file = f"{base}_checkpoint.json"
        
        # 加载论文
        with jsonlines.open(input_file) as f:
            papers = list(f)
        total = len(papers)
        
        # 检查checkpoint
        start_idx = 0
        all_enriched = []
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, 'r') as f:
                    checkpoint = __import__('json').load(f)
                start_idx = checkpoint.get('last_processed', 0)
                if os.path.exists(output_file):
                    with jsonlines.open(output_file) as f:
                        all_enriched = list(f)
                print(f"[RESUME] Found checkpoint, resuming from paper {start_idx+1}/{total}")
            except:
                print(f"[WARN] Failed to load checkpoint, starting from beginning")
                start_idx = 0
                all_enriched = []
        
        remaining = total - start_idx
        if remaining == 0:
            print(f"[SKIP] All {total} papers already processed")
            continue
        
        print(f"Total: {total} papers, Remaining: {remaining} papers")
        print(f"Workers: {max_workers}, Batch size: {batch_size}")
        print(f"Output: {output_file}")
        
        # 处理剩余论文
        current_workers = max_workers
        current_batch_size = batch_size
        consecutive_errors = 0
        
        for start in range(start_idx, total, current_batch_size):
            end = min(start + current_batch_size, total)
            batch = papers[start:end]
            batch_num = (start // current_batch_size) + 1
            total_batches = (total + current_batch_size - 1) // current_batch_size
            
            print(f"\n  [Batch {batch_num}/{total_batches}] Papers {start+1}-{end}/{total} (workers={current_workers})")
            print(f"  {'-'*60}")
            
            batch_start = time.time()
            
            try:
                enriched_batch = enrich_papers_concurrent(batch, max_workers=current_workers)
                all_enriched.extend(enriched_batch)
                
                batch_time = time.time() - batch_start
                avg_time = batch_time / len(batch)
                
                # 成功，重置错误计数
                consecutive_errors = 0
                
                # 保存进度
                with open(checkpoint_file, 'w') as f:
                    __import__('json').dump({'last_processed': end, 'timestamp': time.time()}, f)
                
                # 保存中间结果
                with jsonlines.open(output_file, 'w') as f:
                    for p in all_enriched:
                        f.write(p)
                
                print(f"  ✓ Done in {batch_time:.1f}s ({avg_time:.1f}s/paper), saved checkpoint")
                
                # 如果速度太快，稍微休息
                if avg_time < 0.5 and current_workers >= 8:
                    print(f"  [Throttling] Too fast, resting 3s...")
                    time.sleep(3)
                else:
                    time.sleep(1)
                    
            except Exception as e:
                print(f"  [ERROR] Batch {batch_num} failed: {e}")
                consecutive_errors += 1
                
                # 连续错误，降低并发
                if consecutive_errors >= 2 and current_workers > 2:
                    current_workers = max(2, current_workers - 2)
                    current_batch_size = max(20, current_batch_size - 10)
                    print(f"  [ADAPT] Reducing workers to {current_workers}, batch to {current_batch_size}")
                    time.sleep(10)  # 长休息
                else:
                    time.sleep(5)
                
                # 标记这批为失败
                for p in batch:
                    p['author_enrichment_status'] = 'error'
                    p['enrichment_error'] = str(e)
                    all_enriched.append(p)
        
        # 完成，删除checkpoint
        if os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)
        
        # 最终统计
        success = sum(1 for p in all_enriched if p.get('author_enrichment_status') == 'enriched')
        seniors = sum(p.get('senior_author_count', 0) for p in all_enriched)
        print(f"\n  [COMPLETE] Success: {success}/{total}, Seniors: {seniors}")
    
    # 最终保存数据库
    db.save_databases()
    print(f"\n{'='*80}")
    print(f"ALL FILES PROCESSED!")
    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='Robust batch enrichment with auto-throttling and resume',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
特点:
  - 自动降速: 遇到错误自动降低并发数
  - 断点续传: 中断后重新运行会从上次位置继续
  - 自动保存: 每批完成后自动保存结果

示例:
  python batch_enrich_robust.py file1.jsonl file2.jsonl
  python batch_enrich_robust.py file*.jsonl -w 3 -b 30
        """
    )
    parser.add_argument('files', nargs='+', help='Input JSONL files')
    parser.add_argument('-w', '--workers', type=int, default=5, 
                       help='Initial workers (default: 5)')
    parser.add_argument('-b', '--batch-size', type=int, default=50,
                       help='Batch size (default: 50)')
    
    args = parser.parse_args()
    
    batch_enrich_robust(args.files, args.workers, args.batch_size)


if __name__ == '__main__':
    main()
