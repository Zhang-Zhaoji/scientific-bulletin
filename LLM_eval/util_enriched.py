# -*- coding: utf-8 -*-
"""
Extended utilities for enriched paper data
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
from util import Paper


@dataclass
class EnrichedPaper(Paper):
    """增强的论文数据结构，包含作者信息"""
    affiliations: List[str] = None
    author_details: List[Dict] = None
    senior_authors: List[Dict] = None
    senior_author_count: int = 0
    has_senior_researcher: bool = False
    countries: List[str] = None
    author_enrichment_status: str = ""
    
    @classmethod
    def from_json(cls, data: Dict) -> "EnrichedPaper":
        base = super().from_json(data)
        return cls(
            raw_data=data,
            title=base.title,
            authors=base.authors,
            date=base.date,
            abstract=base.abstract,
            journal=base.journal,
            affiliations=data.get("affiliations", []),
            author_details=data.get("author_details", []),
            senior_authors=data.get("senior_authors", []),
            senior_author_count=data.get("senior_author_count", 0),
            has_senior_researcher=data.get("has_senior_researcher", False),
            countries=data.get("countries", []),
            author_enrichment_status=data.get("author_enrichment_status", "")
        )
    
    def get_senior_author_summary(self) -> str:
        """生成大牛作者摘要"""
        if not self.senior_authors:
            return "无知名学者"
        
        summaries = []
        for sr in self.senior_authors[:3]:  # 最多显示3个
            name = sr.get('name', '')
            h_idx = sr.get('h_index', 'N/A')
            inst = sr.get('institution', '')
            if inst:
                # 只取第一个分号前的部分
                inst_short = inst.split(';')[0][:50]
                summaries.append(f"{name}(h={h_idx}, {inst_short})")
            else:
                summaries.append(f"{name}(h={h_idx})")
        
        return "; ".join(summaries)
    
    def get_affiliation_summary(self) -> str:
        """生成单位摘要"""
        if not self.affiliations:
            return "未知单位"
        
        # 提取主要机构名称（简化）
        institutions = []
        for affil in self.affiliations[:3]:  # 最多显示3个
            # 尝试提取大学/研究所名称
            if 'University' in affil or 'Institute' in affil or 'College' in affil:
                # 取前50字符
                inst_short = affil[:50] + "..." if len(affil) > 50 else affil
                institutions.append(inst_short)
        
        if not institutions and self.affiliations:
            institutions = [self.affiliations[0][:50]]
        
        return "; ".join(institutions) if institutions else "未知单位"
    
    def get_country_summary(self) -> str:
        """生成国家摘要"""
        if not self.countries:
            return "未知"
        return ", ".join(self.countries)


def format_author_info_for_prompt(paper_data: Dict) -> str:
    """
    格式化作者信息供 LLM prompt 使用
    """
    sections = []
    
    # 大牛作者信息
    senior_authors = paper_data.get('senior_authors', [])
    if senior_authors:
        sections.append("【知名学者信息】")
        for sr in senior_authors:
            name = sr.get('name', '')
            h_idx = sr.get('h_index', 'N/A')
            cites = sr.get('citations', 'N/A')
            works = sr.get('works_count', 'N/A')
            inst = sr.get('institution', 'N/A')
            
            sections.append(f"- {name}:")
            sections.append(f"  - h-index: {h_idx}, 总引用: {cites}, 发表作品: {works}")
            if inst and inst != 'N/A':
                # 分割长单位名
                inst_parts = inst.split(';')
                if len(inst_parts) > 1:
                    sections.append(f"  - 所属机构: {inst_parts[0]} 等")
                else:
                    sections.append(f"  - 所属机构: {inst[:80]}")
    
    # 国家信息
    countries = paper_data.get('countries', [])
    if countries:
        sections.append(f"\n【研究国家/地区】: {', '.join(countries)}")
    
    # 单位数量
    affiliations = paper_data.get('affiliations', [])
    if affiliations:
        sections.append(f"【涉及机构数】: {len(affiliations)}")
    
    return "\n".join(sections)
