# -*- coding: utf-8 -*-
"""
NeuroScience Paper Curator - Batch LLM Processing System
Optimized for DeepSeek API with local fallback support
"""

from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, asdict
from enum import Enum
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('curator.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

    

class DomainType(str, Enum):
    CORE = "核心域"
    CROSS_HIGH_IMPACT = "域外高影响"
    CROSS_LIMITED = "域外局限"

class DomainCategory(Enum):
    """Multiple Domain"""
    COGNITIVE = "认知神经科学"
    SYSTEMS = "系统与环路神经科学"
    MOLECULAR = "分子与细胞神经科学"
    DEVELOPMENT = "发育神经科学"
    SENSORIMOTOR = "感觉与运动神经科学"
    COMPUTATIONAL = "计算与理论神经科学"
    CLINICAL = "临床与转化神经科学"
    SOCIAL_AFFECTIVE = "社会与情感神经科学"
    METHODOLOGY = "方法学"

@dataclass
class Paper:
    """论文数据结构"""
    raw_data: Dict
    title: str
    authors: List[str]
    date: str
    abstract: str
    journal: str = ""
    
    @classmethod
    def from_json(cls, data: Dict) -> "Paper":
        return cls(
            raw_data=data,
            title=data.get("title", ""),
            authors=data.get("authors", []),
            date=data.get("date", ""),
            abstract=data.get("abstract", ""),
            journal=data.get("journal", data.get("source", ""))
        )

@dataclass
class PaperResult:
    """分析结果结构"""
    paper_id: str
    domain: str
    primary_category: str
    secondary_category: Optional[str]
    cross_tags: List[str]
    scores: Dict[str, float]
    total_score: float
    recommendation_tier: str
    confidence: float
    reasoning: str
    feature_angle: str
    model_used: str
