# -*- coding: utf-8 -*-
"""
NeuroScience Paper Curator - Batch LLM Processing System
Optimized for DeepSeek API with local fallback support
"""

from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import os
from dotenv import load_dotenv
from config import API_KEY_ENV, BASE_URL_ENV, BASE_URLS, ENV_FILES



def load_api_url(PLATFORM:str)->tuple[str,str]:
    # 加载环境变量
    for env_file in ENV_FILES:
        load_dotenv(env_file, override=True)
    load_dotenv(f".env.{PLATFORM}", override=True)  # optional runtime override

    if PLATFORM not in API_KEY_ENV:
        raise RuntimeError(f'not supported platform {PLATFORM}')

    api_key_env = API_KEY_ENV[PLATFORM]
    base_url_env = BASE_URL_ENV[PLATFORM]
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"{api_key_env} not set")
    base_url = os.getenv(base_url_env, BASE_URLS[PLATFORM])
    return api_key, base_url


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
            journal=data.get("source", data.get("original_source", data.get("journal", "NA")))
        )

@dataclass
class PaperResult:
    """分析结果结构"""
    paper: Paper
    title_zh: str
    paper_id: str
    domain: str
    primary_category: str
    secondary_category: Optional[str]
    cross_tags: List[str]
    scores: Dict[str, float]
    total_score: float
    recommendation_tier: str
    recommendation_text: str
    confidence: float
    reasoning: str
    feature_angle: str
    model_used: str
    key_strength: str
    key_limitation: str
    target_audience: str
    crossover_value: str
    editor_note: str
    cross_domain_potential: float = 0.0
