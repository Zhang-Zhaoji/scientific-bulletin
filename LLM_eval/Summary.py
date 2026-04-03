import json
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime


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
        
        # 生成Markdown报告
        report_path = self.output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_markdown(tiers))
        
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
            "tiers": {k: len(v) for k, v in tiers.items()}
        }
    
    def _generate_markdown(self, tiers: Dict) -> str:
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
        
        # 构建标题（英文+中文翻译）
        md = f"""### {title}"""
        if title_zh:
            md += f"\n**中文标题**: {title_zh}"
        md += "\n\n"
        
        md += f"""**作者**: {', '.join(authors[:3])}{' et al.' if len(authors) > 3 else ''}  
**期刊**: {journal} | **日期**: {date}  
**分类**: {primary_category}"""
        
        if secondary_category:
            md += f" / {secondary_category}"
        
        if cross_tags:
            md += f"\n**标签**: {', '.join(cross_tags[:5])}"
        
        # 显示推荐等级
        if recommendation_tier:
            md += f"\n**推荐等级**: {recommendation_tier}"
        
        if detailed:
            md += f"""

**评分**: {total_score:.1f}/10  
**亮点**: {feature_angle}
"""
            
            # 添加优势、局限和目标受众
            if key_strength:
                md += f"\n**核心优势**: {key_strength}"
            if key_limitation:
                md += f"\n**主要局限**: {key_limitation}"
            if target_audience:
                md += f"\n**目标读者**: {target_audience}"
            
            # 为头条和深度解读添加推荐文本
            if show_recommendation and recommendation_text:
                md += f"\n\n**推荐理由**: {recommendation_text}"
            
            md += "\n\n"
            
            if crossover and domain == "域外高影响":
                md += "**跨界价值**: 该研究虽非神经科学领域，但可能为神经科学带来重要方法学或理论启发。\n\n"
        else:
            md += f"\n**评分**: {total_score:.1f}/10 | **要点**: {feature_angle}"
            
            # 简要提及显示简洁版信息
            if key_strength or key_limitation or target_audience:
                md += "\n"
                if key_strength:
                    md +=  f"**优势**: {key_strength}\n"
                if key_limitation:
                    md +=  f"**局限**: {key_limitation}\n"
                if target_audience:
                    md +=  f"**受众**: {target_audience}"
            
            md += "\n\n"
        
        return md


def main():
    """主函数"""
    # 读取结果文件
    result_file = Path(r"LLM_Results\LLM_results_20260328_004204.json")
    if not result_file.exists():
        print(f"结果文件不存在: {result_file}")
        return
    
    # 创建报告生成器
    generator = ReportGenerator(output_dir=r".\LLM_Results")
    
    # 生成报告
    report = generator.generate_from_json(str(result_file))
    
    # 打印统计信息
    print("报告生成完成！")
    print(f"Markdown报告路径: {report['markdown_path']}")
    print("统计信息:")
    print(f"- 总文章数: {report['statistics']['total']}")
    print(f"- 头条推荐: {report['statistics']['headline']}")
    print(f"- 深度解读: {report['statistics']['deep']}")
    print(f"- 简要提及: {report['statistics']['brief']}")
    print(f"- 跨界启发: {report['statistics']['crossover']}")
    print(f"- 已过滤: {report['statistics']['rejected']}")
    print(f"- 平均评分: {report['statistics']['avg_score']:.2f}")
    from call_API import LLM_process
    from dotenv import load_dotenv
    import os
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY not set")
    base_url = os.getenv("API_BASE_URL")
    if not base_url:
        raise ValueError("API_BASE_URL not set")

    LLM_engine = LLM_process(api_key=api_key, base_url=base_url, model="qwen3.5-plus-2026-02-15")
    System_prompt = "你是一个专业的神经科学论文编辑，下面是最新一周的神经科学简报内容，按照不同等级进行了推荐。你被要求从推荐中找到几个最让人关心的内容来生成标题。"
    main_text_md = report['markdown_path']
    with open(main_text_md, "r", encoding="utf-8") as f:
        main_text_md = f.read()
    User_prompt = f"下面是神经科学简报内容：{main_text_md} 请根据以上内容，生成标题。"
    response = LLM_engine.client.chat.completions.parse(
            model = LLM_engine.model,
            messages=[
                    {"role": "system", "content": System_prompt},
                    {"role": "user", "content": User_prompt},
                ],
            extra_body={"enable_thinking":True}
            )
    result = response.choices[0].message.content
    print(result)


if __name__ == "__main__":
    main()
