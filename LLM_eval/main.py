from dotenv import load_dotenv
import os
import json
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

# 测试文件路径
test_file = Path(r"D:\工作\scientific bulletin\getfiles\all_papers_2026-03-14.jsonl")


def process_article(article_info):
    """处理单篇文章"""
    # 初始化 LLM 处理器
    llm_api = LLM_process(api_key=api_key, base_url=base_url, model="qwen3.5-plus")
    
    # 初始化提示词生成器
    prompt_generator = PromptGenerator()
    
    # 初始化文章处理器
    article_processor = ArticleProcess(article_info)
    
    # 处理文章
    result = article_processor.process(prompt_generator, llm_api)
    
    return result


def main():
    """主函数"""
    print("开始处理文章...")
    
    # 读取测试文件
    with open(test_file, 'r', encoding='utf-8') as f:
        articles = [json.loads(line) for line in f if line.strip()]
    for article in articles:
        if '\n' in article['title']:
            article['title'] = article['title'].replace('\n', ' ')
        while '  ' in article['title']:
            article['title'] = article['title'].replace('  ', ' ') # 替换多个空格为一个空格
    
    print(f"共读取到 {len(articles)} 篇文章")
    
    # 处理每篇文章
    results = []
    for i, article in enumerate(tqdm.tqdm(articles, desc="处理文章", total=len(articles))):
        print(f"处理第 {i+1} 篇文章: {article.get('title', '未知标题')}")
        result = process_article(article)
        results.append(result)
        print(f"处理完成，推荐等级: {result.recommendation_tier}")
    
    # 保存结果
    if results:
        # 保存为 JSON 文件
        output_file = results_dir / f"LLM_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(result) for result in results], f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {output_file}")
    else:
        print("没有处理结果")


if __name__ == "__main__":
    main()
