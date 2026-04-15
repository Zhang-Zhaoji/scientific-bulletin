"""
Batch Enrichment with API Keys - Faster processing

使用API Key提高速率限制:
- PubMed: 10 requests/sec (需要 NCBI API Key)
- OpenAlex: 10 requests/sec (使用 polite mode)

获取 NCBI API Key:
1. 访问 https://www.ncbi.nlm.nih.gov/account/
2. 注册/登录账户
3. 在 Account Settings 中创建 API Key
4. 将 key 保存到环境变量或 .env 文件: NCBI_API_KEY=your_key_here
"""

import argparse
import jsonlines
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enrich_authors import enrich_papers_concurrent, get_db


def batch_enrich_with_key(input_files: list, max_workers: int = 8, batch_size: int = 100):
    """
    使用API Key的批量处理（更快）
    
    Args:
        input_files: 输入文件列表
        max_workers: 最大并发数（建议8-10，有key时）
        batch_size: 每批处理的论文数（默认100）
    """
    
    # 检查 API Key
    ncbi_key = os.environ.get('NCBI_API_KEY', '')
    if ncbi_key:
        print(f"[INFO] NCBI API Key found: {ncbi_key[:5]}...{ncbi_key[-5:]}")
        print(f"[INFO] PubMed rate limit: 10 requests/sec")
    else:
        print(f"[WARN] No NCBI_API_KEY found, using conservative limits")
        print(f"[WARN] PubMed rate limit: 3 requests/sec")
        print(f"[WARN] Consider getting an API key: https://www.ncbi.nlm.nih.gov/account/")
        max_workers = min(max_workers, 3)  # 无key时降低并发
    
    total_start = time.time()
    total_papers = 0
    
    for input_file in input_files:
        print(f"\n{'='*80}")
        print(f"Processing: {os.path.basename(input_file)}")
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
        print(f"Settings: workers={max_workers}, batch_size={batch_size}")
        
        # 分批处理
        all_enriched = []
        batches = list(range(0, total, batch_size))
        file_start = time.time()
        
        for i, start in enumerate(batches):
            end = min(start + batch_size, total)
            batch = papers[start:end]
            
            print(f"\n  [Batch {i+1}/{len(batches)}] Papers {start+1}-{end}/{total}")
            
            batch_start = time.time()
            
            try:
                enriched_batch = enrich_papers_concurrent(batch, max_workers=max_workers)
                all_enriched.extend(enriched_batch)
                
                batch_time = time.time() - batch_start
                avg_time = batch_time / len(batch)
                print(f"  ✓ Completed in {batch_time:.1f}s ({avg_time:.1f}s per paper)")
                
                # 估计剩余时间
                remaining_batches = len(batches) - i - 1
                if remaining_batches > 0:
                    est_remaining = remaining_batches * batch_time
                    print(f"  [Est] ~{est_remaining/60:.1f} minutes remaining for this file")
                
                # 短休息，让API喘口气
                if i < len(batches) - 1:
                    time.sleep(2)
                    
            except Exception as e:
                print(f"  [ERROR] Batch {i+1} failed: {e}")
                for p in batch:
                    p['author_enrichment_status'] = 'error'
                    p['enrichment_error'] = str(e)
                    all_enriched.append(p)
        
        # 保存结果
        print(f"\n  Saving {len(all_enriched)} papers...")
        with jsonlines.open(output_file, 'w') as f:
            for p in all_enriched:
                f.write(p)
        
        file_time = time.time() - file_start
        success = sum(1 for p in all_enriched if p.get('author_enrichment_status') == 'enriched')
        seniors = sum(p.get('senior_author_count', 0) for p in all_enriched)
        
        print(f"  [OK] Done! {success}/{total} enriched, {seniors} senior authors found")
        print(f"  [Time] {file_time/60:.1f} minutes ({file_time/total:.1f}s per paper)")
        
        total_papers += total
        
        # 文件之间休息
        if input_file != input_files[-1]:
            print(f"\n[Resting 10s before next file...]")
            time.sleep(10)
    
    # 最终保存
    db = get_db()
    db.save_databases()
    
    total_time = time.time() - total_start
    print(f"\n{'='*80}")
    print(f"ALL DONE!")
    print(f"  Total files: {len(input_files)}")
    print(f"  Total papers: {total_papers}")
    print(f"  Total time: {total_time/60:.1f} minutes")
    print(f"  Avg speed: {total_time/total_papers:.1f}s per paper")
    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='Fast batch enrichment with API keys',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
环境变量:
  NCBI_API_KEY    Your NCBI API key (optional but recommended)

示例:
  # 无API Key（较慢）
  python batch_enrich_with_key.py file1.jsonl file2.jsonl
  
  # 有API Key（较快）
  set NCBI_API_KEY=your_key_here
  python batch_enrich_with_key.py file1.jsonl file2.jsonl -w 10
  
  # 或者
  python batch_enrich_with_key.py file1.jsonl file2.jsonl -w 5 -b 50
        """
    )
    parser.add_argument('files', nargs='+', help='Input JSONL files')
    parser.add_argument('-w', '--workers', type=int, default=8, 
                       help='Concurrent workers (default: 8 with key, 3 without)')
    parser.add_argument('-b', '--batch-size', type=int, default=100,
                       help='Papers per batch (default: 100)')
    
    args = parser.parse_args()
    
    batch_enrich_with_key(args.files, args.workers, args.batch_size)


if __name__ == '__main__':
    main()
