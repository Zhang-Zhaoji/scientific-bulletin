import os
import json
import argparse
from pathlib import Path
from dataclasses import asdict
from call_API import LLM_process, ArticleProcess
from StructuredPrompt import PromptGenerator
import datetime
import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from util import load_api_url
from config import PLATFORM as DEFAULT_PLATFORM, default_model, supported_platforms

# 创建结果目录
results_dir = Path("LLM_Results")
results_dir.mkdir(parents=True, exist_ok=True)


def clean_article(article: dict) -> dict:
    """清理文章标题中的换行符和多余空格"""
    if '\n' in article.get('title', ''):
        article['title'] = article['title'].replace('\n', ' ')
    while '  ' in article.get('title', ''):
        article['title'] = article['title'].replace('  ', ' ')
    return article


def process_article(llm_api, prompt_generator, article_info):
    """处理单篇文章"""
    article_processor = ArticleProcess(article_info)
    result = article_processor.process(prompt_generator, llm_api)
    return result


def worker(article, llm_api, prompt_generator, max_retries=15):
    """单篇文章处理（带重试），供线程池调用"""
    for retry in range(max_retries):
        try:
            result = process_article(llm_api, prompt_generator, article)
            return result, None
        except Exception as e:
            if retry < max_retries - 1:
                time.sleep(2 * (retry + 1))
            else:
                return None, str(e)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Process papers with LLM for neuroscience curation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Process default file
  python main.py -i papers.jsonl          # Process specific file
  python main.py -i papers.jsonl -l 10    # Process only first 10 papers
  python main.py -i papers.jsonl -w 20    # 20 parallel workers
        """
    )
    
    parser.add_argument('-i', '--input', 
                        default='getfiles/all_papers_2026-04-18_enriched.jsonl',
                        help='Input JSONL file path')
    parser.add_argument('-o', '--output',
                        help='Output JSON file path (default: auto-generated in LLM_Results)')
    parser.add_argument('-l', '--limit', type=int,
                        help='Limit number of papers to process')
    parser.add_argument('--model',
                        help='LLM model to use (default: configured in LLM_eval/config.py)')
    parser.add_argument('--platform', default=DEFAULT_PLATFORM, choices=supported_platforms(),
                        help=f'Model provider platform (default: {DEFAULT_PLATFORM})')
    parser.add_argument('-w', '--workers', type=int, default=20,
                        help='Number of parallel workers (default: 20)')
    
    args = parser.parse_args()
    if not args.model:
        args.model = default_model(args.platform)
    
    # 确定输入文件
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"错误: 输入文件不存在: {input_file}")
        return
    
    print("=" * 80)
    print("Neuroscience Paper Curation - LLM Processing")
    print("=" * 80)
    print(f"Input file: {input_file}")
    print(f"Platform: {args.platform}")
    print(f"Model: {args.model}")
    print(f"Workers: {args.workers}")
    if args.limit:
        print(f"Limit: {args.limit} papers")
    print()
    
    # 读取文件
    print("Loading papers...")
    with open(input_file, 'r', encoding='utf-8') as f:
        articles = [clean_article(json.loads(line)) for line in f if line.strip()]
    
    # 应用限制
    if args.limit:
        articles = articles[:args.limit]
        print(f"Loaded {len(articles)} papers (limited from original)")
    else:
        print(f"Loaded {len(articles)} papers")
    
    # 检查是否是 enriched 文件
    has_author_enrichment = any(
        article.get('author_enrichment_status') == 'enriched' 
        for article in articles[:5]
    )
    if has_author_enrichment:
        print("[INFO] Detected enriched file with author information")
    
    # 初始化 LLM
    api_key, base_url = load_api_url(PLATFORM=args.platform)
    llm_api = LLM_process(api_key=api_key, base_url=base_url, model=args.model, provider=args.platform)
    
    # 初始化提示词生成器
    prompt_generator = PromptGenerator()
    
    # 确定输出文件
    if args.output:
        output_file = Path(args.output)
    else:
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = results_dir / f"LLM_results_{timestamp}.json"
    
    # 并行处理
    print(f"\nProcessing papers with {args.workers} workers...")
    total = len(articles)
    results = [None] * total  # 按索引保存，保持顺序
    failed = [None] * total
    completed = 0
    saved_count = 0
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # 提交所有任务
        future_to_idx = {
            executor.submit(worker, article, llm_api, prompt_generator): i
            for i, article in enumerate(articles)
        }
        
        # 按完成顺序收集结果（但按索引存储保持顺序）
        with tqdm.tqdm(total=total, desc="Processing") as pbar:
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                result, error = future.result()
                results[idx] = result
                failed[idx] = error
                completed += 1
                pbar.update(1)
                
                # 每100篇保存一次（增量保存，防止中断丢失）
                if completed % 100 == 0 and completed < total:
                    valid = [r for r in results if r is not None]
                    if valid:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump([asdict(r) for r in valid], f, ensure_ascii=False, indent=2)
                        saved_count = len(valid)
                        print(f"  [Checkpoint] Saved {saved_count} results ({completed}/{total} processed)")
    
    # 过滤掉失败的结果
    valid_results = [(i, r) for i, r in enumerate(results) if r is not None]
    failed_results = [(i, failed[i]) for i in range(total) if results[i] is None]
    
    # 保存最终结果
    if valid_results:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(r) for _, r in valid_results], f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 80)
        print("Processing Complete!")
        print("=" * 80)
        print(f"Results saved to: {output_file}")
        print(f"Total processed: {len(valid_results)}/{total}")
        if failed_results:
            print(f"Failed: {len(failed_results)}")
            for i, err in failed_results[:5]:
                print(f"  [{i}] {articles[i].get('title', 'Unknown')[:50]}...: {err[:80]}")
        
        # 统计推荐等级
        tier_counts = {}
        for _, r in valid_results:
            tier = r.recommendation_tier
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        print("\nRecommendation distribution:")
        for tier, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
            print(f"  - {tier}: {count}")
    else:
        print("\n[WARNING] No results to save")


if __name__ == "__main__":
    main()
