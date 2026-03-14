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
    
    def generate(self, papers: List[Paper], results: List[AnalysisResult]) -> Dict:
        """生成完整报告"""
        
        # 按推荐等级分组
        tiers = {
            "头条推荐": [],
            "深度解读": [],
            "简要提及": [],
            "域外高影响": [],
            "不推送": [],
            "错误": []
        }
        
        for paper, result in zip(papers, results):
            if result.recommendation_tier in tiers:
                tiers[result.recommendation_tier].append((paper, result))
            else:
                tiers["不推送"].append((paper, result))
        
        # 生成Markdown报告
        report_path = self.output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_markdown(tiers))
        
        # 生成JSON数据（用于后续自动化）
        json_path = self.output_dir / f"data_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        
        export_data = []
        for paper, result in zip(papers, results):
            export_data.append({
                "paper": asdict(paper),
                "analysis": asdict(result)
            })
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        # 生成统计摘要
        stats = {
            "total": len(papers),
            "headline": len(tiers["头条推荐"]),
            "deep": len(tiers["深度解读"]),
            "brief": len(tiers["简要提及"]),
            "crossover": len(tiers["域外高影响"]),
            "rejected": len(tiers["不推送"]) + len(tiers["错误"]),
            "avg_score": sum(r.total_score for r in results if r.total_score > 0) / max(1, sum(1 for r in results if r.total_score > 0))
        }
        
        return {
            "markdown_path": str(report_path),
            "json_path": str(json_path),
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
        
        # 头条推荐
        if tiers["头条推荐"]:
            md += "## 🥇 头条推荐（9.0+分）\n\n"
            for paper, result in tiers["头条推荐"]:
                md += self._format_paper_entry(paper, result, detailed=True)
            md += "---\n\n"
        
        # 深度解读
        if tiers["深度解读"]:
            md += "## 🔬 深度精选（8.0-8.9分）\n\n"
            for paper, result in tiers["深度解读"]:
                md += self._format_paper_entry(paper, result, detailed=True)
            md += "---\n\n"
        
        # 域外高影响
        if tiers["域外高影响"]:
            md += "## 🌉 跨界高影响（域外精选）\n\n"
            for paper, result in tiers["域外高影响"]:
                md += self._format_paper_entry(paper, result, detailed=True, crossover=True)
            md += "---\n\n"
        
        # 简要提及
        if tiers["简要提及"]:
            md += "## 📋 领域速递（7.0-7.9分）\n\n"
            for paper, result in tiers["简要提及"]:
                md += self._format_paper_entry(paper, result, detailed=False)
            md += "---\n\n"
        
        # 附录：已过滤文章（可选，用于编辑参考）
        if tiers["不推送"]:
            md += "## 🚫 本周过滤（编辑参考）\n\n"
            md += "<details>\n<summary>点击展开（仅内部参考）</summary>\n\n"
            for paper, result in tiers["不推送"][:10]:  # 只显示前10篇
                md += f"- **{paper.title}** | 得分：{result.total_score:.1f} | 原因：{result.reasoning[:50]}...\n"
            if len(tiers["不推送"]) > 10:
                md += f"\n... 还有 {len(tiers['不推送']) - 10} 篇未显示\n"
            md += "</details>\n"
        
        return md
    
    def _format_paper_entry(
        self, 
        paper: Paper, 
        result: AnalysisResult, 
        detailed: bool = True,
        crossover: bool = False
    ) -> str:
        """格式化单篇论文条目"""
        
        md = f"""### {paper.title}
**作者**: {', '.join(paper.authors[:3])}{' et al.' if len(paper.authors) > 3 else ''}  
**期刊**: {paper.journal} | **日期**: {paper.date}  
**分类**: {result.primary_category}"""
        
        if result.secondary_category:
            md += f" / {result.secondary_category}"
        
        md += f"\n**标签**: {', '.join(result.cross_tags[:5])}\n"
        
        if detailed:
            md += f"""
**评分**: {result.total_score:.1f}/10  
**亮点**: {result.feature_angle}

"""
            if crossover and result.domain == "域外高影响":
                md += "**跨界价值**: 该研究虽非神经科学领域，但可能为神经科学带来重要方法学或理论启发。\n\n"
        else:
            md += f"**得分**: {result.total_score:.1f} | **要点**: {result.feature_angle}\n\n"
        
        return md
