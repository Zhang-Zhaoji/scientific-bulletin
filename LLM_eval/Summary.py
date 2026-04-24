import json
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
import argparse
import os
import sys

# 添加visualize目录到路径，方便导入统计模块
sys.path.append(os.path.join(os.path.dirname(__file__), '../visualize'))
from dbapi import DBAPI
from vis_stat import StatisticsVisualizer


class ReportGenerator:
    """生成微信推送报告"""
    
    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_from_json(self, json_file: str) -> Dict:
        """从JSON文件生成报告"""
        # 读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # 按推荐等级分组
        tiers = {
            "头条推荐": [],
            "深度解读": [],
            "简要提及": [],
            "域外高影响": [],
            "不推送": [],
            "错误": []
        }
        
        total_score = 0
        scored_papers = 0
        
        for result in results:
            recommendation_tier = result.get("recommendation_tier", "不推送")
            if recommendation_tier in tiers:
                tiers[recommendation_tier].append(result)
            else:
                tiers["不推送"].append(result)
            
            # 计算总分
            if result.get("total_score", 0) > 0:
                total_score += result.get("total_score", 0)
                scored_papers += 1
        
        # 获取日期范围（从结果中提取最早和最晚的日期）
        dates = []
        for result in results:
            date = result.get('paper', {}).get('date', None)
            if date and len(date) >= 10:
                dates.append(date[:10])
        start_date = min(dates) if dates else None
        end_date = max(dates) if dates else None
        
        # 先初始化，确保即使失败也有定义
        statistics_text = ""
        
        # 生成统计信息文字和可视化
        try:
            db_api = DBAPI()
            stats_vis = StatisticsVisualizer(db_api)
            
            # 获取国家统计
            country_stats = db_api.get_country_article_count(start_date, end_date)
            
            # 获取机构TOP 10
            institution_stats = stats_vis.get_institution_topn(start_date, end_date, top_n=10)
            
            # 获取评分分布
            score_stats = stats_vis.get_score_distribution(results)
            
            # 生成可视化图表（HTML）
            stats_vis.render_score_histogram(score_stats)
            statistics_text += "### 📊 可视化图表\n\n"
            
            # 生成统计文字
            statistics_text = stats_vis.get_statistics_text(country_stats[:10], institution_stats, score_stats)
        except Exception as e:
            print(f"[WARNING] 生成统计图表失败: {e}")
            statistics_text = ""
        finally:
            if 'db_api' in locals():
                db_api.close()
        
        # 生成Markdown报告
        report_path = self.output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        self.report_path = report_path
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_markdown(tiers, statistics_text))
        
        # 生成统计摘要
        stats = {
            "total": len(results),
            "headline": len(tiers["头条推荐"]),
            "deep": len(tiers["深度解读"]),
            "brief": len(tiers["简要提及"]),
            "crossover": len(tiers["域外高影响"]),
            "rejected": len(tiers["不推送"]) + len(tiers["错误"]),
            "avg_score": total_score / max(1, scored_papers)
        }
        
        return {
            "markdown_path": str(report_path),
            "statistics": stats,
            "statistics_text": statistics_text,
            "tiers": {k: len(v) for k, v in tiers.items()}
        }
    
    def _generate_markdown(self, tiers: Dict, statistics_text: str = "") -> str:
        """生成Markdown格式报告"""
        
        md = f"""# 神经科学文献策展报告
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 📊 本周概览

- **头条推荐**: {len(tiers['头条推荐'])} 篇
- **深度解读**: {len(tiers['深度解读'])} 篇  
- **简要提及**: {len(tiers['简要提及'])} 篇
- **跨界启发**: {len(tiers['域外高影响'])} 篇
- **已过滤**: {len(tiers['不推送']) + len(tiers['错误'])} 篇

---

{statistics_text}

"""
        
        # 统计每个子领域的文章数量
        deep_results = tiers.get("深度解读", [])
        brief_results = tiers.get("简要提及", [])
        all_selected = deep_results + brief_results
        
        # 按领域统计数量
        domain_stats = {}
        for result in all_selected:
            domain = result.get("primary_category", "未知领域") or "未知领域"
            if domain not in domain_stats:
                domain_stats[domain] = {"深度解读": 0, "简要提及": 0, "总计": 0}
            
            recommendation_tier = result.get("recommendation_tier", "")
            if recommendation_tier == "深度解读":
                domain_stats[domain]["深度解读"] += 1
            elif recommendation_tier == "简要提及":
                domain_stats[domain]["简要提及"] += 1
            domain_stats[domain]["总计"] += 1
        
        # 添加领域统计表格
        if domain_stats:
            md += "## 📈 各领域文章分布\n\n"
            md += "| 领域 | 深度解读 | 简要提及 | 总计 |\n"
            md += "|------|----------|----------|------|\n"
            
            # 按总数排序
            for domain, stats in sorted(domain_stats.items(), key=lambda x: x[1]["总计"], reverse=True):
                md += f"| {domain} | {stats['深度解读']} | {stats['简要提及']} | {stats['总计']} |\n"
            
            md += f"\n**合计**: 深度解读 {sum(s['深度解读'] for s in domain_stats.values())} 篇，简要提及 {sum(s['简要提及'] for s in domain_stats.values())} 篇，共 {sum(s['总计'] for s in domain_stats.values())} 篇\n\n"
            md += "---\n\n"
        
        # 头条推荐 - 按分数从高到低排序
        if tiers["头条推荐"]:
            md += "## 🥇 头条推荐（9.0+分）\n\n"
            # 按分数排序
            sorted_headlines = sorted(tiers["头条推荐"], key=lambda x: x.get("total_score", 0), reverse=True)
            for result in sorted_headlines:
                md += self._format_paper_entry(result, detailed=True, show_recommendation=True)
            md += "---\n\n"
        
        # 深度解读和简要提及合并 - 按领域分类，再按分数排序
        if all_selected:
            md += "## 📚 精选文献（按领域分类）\n\n"
            
            # 按领域分组
            domain_groups = {}
            for result in all_selected:
                domain = result.get("primary_category", result.get("domain", "跨界")) or "跨界"
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(result)
            
            # 对每个领域内的文章按分数排序（高分在前）
            for domain, articles in sorted(domain_groups.items()):
                sorted_articles = sorted(articles, key=lambda x: x.get("total_score", 0), reverse=True)
                md += f"### {domain}\n\n"
                for result in sorted_articles:
                    # 根据推荐等级决定详细程度
                    is_deep = result.get("recommendation_tier") == "深度解读"
                    md += self._format_paper_entry(result, detailed=is_deep, show_recommendation=is_deep)
            md += "---\n\n"
        
        # 域外高影响
        if tiers["域外高影响"]:
            md += "## 🌉 跨界高影响（域外精选）\n\n"
            for result in tiers["域外高影响"]:
                md += self._format_paper_entry(result, detailed=True, crossover=True)
            md += "---\n\n"
        
        return md
    
    def _format_paper_entry(
        self, 
        result: Dict, 
        detailed: bool = True,
        crossover: bool = False,
        show_recommendation: bool = False
    ) -> str:
        """格式化单篇论文条目"""
        
        # 从结果中提取信息
        title = result.get("paper", {}).get("title", "未知标题")
        title_zh = result.get("title_zh", "")  # 中文标题翻译
        authors = result.get("paper", {}).get("authors", [])
        journal = result.get("paper", {}).get("journal", "未知期刊")
        date = result.get("paper", {}).get("date", "未知日期")
        primary_category = result.get("primary_category", "跨界")
        secondary_category = result.get("secondary_category", None)
        cross_tags = result.get("cross_tags", [])
        total_score = result.get("total_score", 0)
        feature_angle = result.get("feature_angle", "")
        domain = result.get("domain", "")
        recommendation_tier = result.get("recommendation_tier", "")
        
        # 新增字段
        key_strength = result.get("key_strength", "")
        key_limitation = result.get("key_limitation", "")
        target_audience = result.get("target_audience", "")
        recommendation_text = result.get("recommendation_text", "")
        
        # 提取作者增强信息
        paper_raw = result.get("paper", {}).get("raw_data", {})
        senior_authors = paper_raw.get("senior_authors", [])
        countries = paper_raw.get("countries", [])
        affiliations = paper_raw.get("affiliations", [])
        
        # 构建标题（英文+中文翻译）
        md = f"""### {title}"""
        if title_zh:
            md += f"\n\n**中文标题**: {title_zh}"
        md += "\n\n"
        
        # 作者信息
        md += f"**作者**: {', '.join(authors[:3])}{' et al.' if len(authors) > 3 else ''}"
        
        # 机构/工作单位信息
        if affiliations:
            md += "\n\n**单位**: "
            unique_affiliations = list(set(affiliations[:3]))  # 去重，最多显示3个单位
            md += "; ".join(unique_affiliations)
            if len(affiliations) > 3:
                md += " 等"
        elif senior_authors:
            # 如果没有全局affiliations，尝试从资深作者信息提取
            author_institutions = []
            for sr in senior_authors[:2]:
                inst = sr.get('institution', '')
                if inst and inst != 'N/A':
                    author_institutions.append(inst)
            if author_institutions:
                md += "\n\n**单位**: " + "; ".join(list(set(author_institutions)))
        
        # 基础信息
        md += f"\n\n**期刊**: {journal} | **发表日期**: {date}"
        
        # 知名学者信息
        if senior_authors:
            md += "\n\n**资深研究者**: "
            senior_summaries = []
            for sr in senior_authors[:2]:  # 最多显示2个
                name = sr.get('name', '')
                h_idx = sr.get('h_index', 'N/A')
                senior_summaries.append(f"{name} (h指数={h_idx})")
            md += "; ".join(senior_summaries)
        
        # 国家信息
        if countries:
            md += f"\n\n**研究地区**: {', '.join(countries)}"
        
        md += f"\n\n**研究领域**: {primary_category}"
        
        if secondary_category:
            md += f" / {secondary_category}"
        
        if cross_tags:
            md += f"\n\n**关键词**: {', '.join(cross_tags[:6])}"
        
        # 显示推荐等级
        if recommendation_tier:
            md += f"\n\n**推荐等级**: {recommendation_tier}"
        
        if detailed:
            md += f"""\n\n

**评分**: {total_score:.1f}/10  \n\n
**亮点**: {feature_angle}
"""
            
            # 添加优势、局限和目标受众
            if key_strength:
                md += f"\n\n**核心优势**: {key_strength}"
            if key_limitation:
                md += f"\n\n**研究局限**: {key_limitation}"
            if target_audience:
                md += f"\n\n**目标读者**: {target_audience}"
            
            # 为头条和深度解读添加推荐文本
            if show_recommendation and recommendation_text:
                md += f"\n\n**推荐理由**: {recommendation_text}"
            
            md += "\n\n"
            
            if crossover and domain == "域外高影响":
                md += f"\n\n**跨界价值**: {result.get('crossover_value', '该研究虽非神经科学领域，但可能为神经科学带来重要方法学或理论启发。')}\n\n"
        else:
            md += f"\n\n**评分**: {total_score:.1f}/10 | **摘要**: {feature_angle}"
            
            # 简要提及显示简洁版信息
            if key_strength or key_limitation or target_audience:
                md += "\n\n"
                if key_strength:
                    md +=  f"**优势**: {key_strength}\n"
                if key_limitation:
                    md +=  f"**局限**: {key_limitation}\n"
                if target_audience:
                    md +=  f"**受众**: {target_audience}"
            
            md += "\n\n"
        
        return md


def find_latest_result(results_dir: Path = Path("./LLM_Results")) -> Optional[Path]:
    """找到最新的 LLM 结果文件"""
    if not results_dir.exists():
        return None
    
    result_files = list(results_dir.glob("LLM_results_*.json"))
    if not result_files:
        return None
    
    # 按修改时间排序
    latest = max(result_files, key=lambda p: p.stat().st_mtime)
    return latest

def add_Enter(md:str) -> str:
    """添加换行符"""
    return md.replace("\n", "\n\n")





def generate_title_with_llm(markdown_path: str):
    """使用 LLM 生成标题"""
    from call_API import LLM_process
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("API_BASE_URL")
    
    if not api_key or not base_url:
        print("[WARNING] API 配置缺失，跳过标题生成")
        return
    
    print("\n正在生成标题...")
    LLM_engine = LLM_process(api_key=api_key, base_url=base_url, model="deepseek-v4-flash")
    
    System_prompt = "你是一个专业的神经科学论文编辑，下面是最新一周的神经科学简报内容，按照不同等级进行了推荐。你被要求从推荐中找到几个最让人关心的内容来生成标题。"
    
    with open(markdown_path, "r", encoding="utf-8") as f:
        main_text_md = f.read()
    
    User_prompt = f"下面是神经科学简报内容：{main_text_md[:3000]}... 请根据以上内容，生成标题。"
    
    try:
        response = LLM_engine.client.chat.completions.parse(
            model=LLM_engine.model,
            messages=[
                {"role": "system", "content": System_prompt},
                {"role": "user", "content": User_prompt},
            ],
            extra_body={"enable_thinking": True}
        )
        result = response.choices[0].message.content
        print("\n" + "=" * 60)
        print("生成的标题:")
        print("=" * 60)
        print(result)
        return result
    except Exception as e:
        print(f"[ERROR] 标题生成失败: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Generate Markdown report from LLM results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python Summary.py                          # Use latest result file
  python Summary.py -i results.json          # Use specific file
  python Summary.py -o ./output              # Specify output directory
        """
    )
    
    parser.add_argument('-i', '--input',
                        help='Input JSON file from LLM processing (default: latest in LLM_Results)')
    parser.add_argument('-o', '--output', default='./LLM_Results',
                        help='Output directory for markdown report (default: ./LLM_Results)')
    parser.add_argument('--title', action='store_true',
                        help='Generate title using LLM (requires API)')
    
    args = parser.parse_args()
    
    # 确定输入文件
    if args.input:
        result_file = Path(args.input)
        if not result_file.exists():
            print(f"错误: 输入文件不存在: {result_file}")
            return
    else:
        # 自动查找最新文件
        result_file = find_latest_result()
        if not result_file:
            print("错误: 未找到 LLM 结果文件，请先用 main.py 处理论文")
            return
        print(f"使用最新的结果文件: {result_file}")
    
    # 创建报告生成器
    generator = ReportGenerator(output_dir=args.output)
    
    # 生成报告
    print(f"\n生成报告 from: {result_file}")
    report = generator.generate_from_json(str(result_file))
    
    # 打印统计信息
    print("\n" + "=" * 60)
    print("报告生成完成！")
    print("=" * 60)
    print(f"Markdown报告路径: {report['markdown_path']}")
    print("\n统计信息:")
    print(f"- 总文章数: {report['statistics']['total']}")
    print(f"- 头条推荐: {report['statistics']['headline']}")
    print(f"- 深度解读: {report['statistics']['deep']}")
    print(f"- 简要提及: {report['statistics']['brief']}")
    print(f"- 跨界启发: {report['statistics']['crossover']}")
    print(f"- 已过滤: {report['statistics']['rejected']}")
    print(f"- 平均评分: {report['statistics']['avg_score']:.2f}")
    
    title = generate_title_with_llm(report['markdown_path'])

    
    with open(generator.report_path, 'r+', encoding="utf-8") as f:
        content = f.read()
        f.seek(0)
        f.write(title + "\n\n" + content)
    

if __name__ == "__main__":
    main()
