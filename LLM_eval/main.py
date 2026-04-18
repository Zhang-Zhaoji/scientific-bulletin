from dotenv import load_dotenv
import os
import json
import argparse
from pathlib import Path
from dataclasses import asdict
from call_API import LLM_process, ArticleProcess
from StructuredPrompt import PromptGenerator
import datetime
import tqdm

# 加载环境变量
load_dotenv()  # load .env file
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    raise ValueError("DASHSCOPE_API_KEY not set")
base_url = os.getenv("API_BASE_URL")
if not base_url:
    raise ValueError("API_BASE_URL not set")

# 创建结果目录
results_dir = Path(r"D:\工作\scientific bulletin\LLM_Results")
results_dir.mkdir(exist_ok=True)


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


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Process papers with LLM for neuroscience curation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Process default file
  python main.py -i papers.jsonl          # Process specific file
  python main.py -i papers_enriched.jsonl # Process enriched file with author info
  python main.py -i papers.jsonl -l 10    # Process only first 10 papers
        """
    )
    
    parser.add_argument('-i', '--input', 
                        default='getfiles/all_papers_2026-04-18_enriched.jsonl',
                        help='Input JSONL file path (default: getfiles/all_papers_2026-04-18_enriched.jsonl)')
    parser.add_argument('-o', '--output',
                        help='Output JSON file path (default: auto-generated in LLM_Results)')
    parser.add_argument('-l', '--limit', type=int,
                        help='Limit number of papers to process')
    parser.add_argument('--model', default='qwen3.6-plus',
                        help='LLM model to use (default: qwen3.6-plus)')
    
    args = parser.parse_args()
    
    # 确定输入文件
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"错误: 输入文件不存在: {input_file}")
        return
    
    print("=" * 80)
    print("Neuroscience Paper Curation - LLM Processing")
    print("=" * 80)
    print(f"Input file: {input_file}")
    print(f"Model: {args.model}")
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
    llm_api = LLM_process(api_key=api_key, base_url=base_url, model=args.model)
    
    # 初始化提示词生成器
    prompt_generator = PromptGenerator()
    
    # 处理每篇文章
    print("\nProcessing papers...")
    results = []
    for i, article in enumerate(tqdm.tqdm(articles, desc="Processing"), 1):
        print(f"\n[{i}/{len(articles)}] {article.get('title', 'Unknown')[:60]}...")
        
        success = False
        retries = 0
        max_retries = 3
        
        while not success and retries < max_retries:
            try:
                result = process_article(llm_api, prompt_generator, article)
                success = True
                print(f"    Recommendation: {result.recommendation_tier}")
            except Exception as e:
                retries += 1
                print(f"    [ERROR] Attempt {retries}/{max_retries}: {e}")
                if retries < max_retries:
                    time.sleep(2 ** retries)  # Exponential backoff
                else:
                    print(f"    [FAILED] Skipping after {max_retries} attempts")
        
        if success:
            results.append(result)
    
    # 保存结果
    if results:
        # 确定输出文件名
        if args.output:
            output_file = Path(args.output)
        else:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = results_dir / f"LLM_results_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(result) for result in results], f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 80)
        print("Processing Complete!")
        print("=" * 80)
        print(f"Results saved to: {output_file}")
        print(f"Total processed: {len(results)}/{len(articles)}")
        
        # 统计推荐等级
        tier_counts = {}
        for r in results:
            tier = r.recommendation_tier
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        print("\nRecommendation distribution:")
        for tier, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
            print(f"  - {tier}: {count}")
    else:
        print("\n[WARNING] No results to save")


if __name__ == "__main__":
    import time  # Import here for retry backoff
    main()
