#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List, Dict
import hashlib
from util import Paper, DomainCategory, DomainType
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal, Optional, Union, List
from enum import Enum
import json


# ── Scoring criteria constants (shared by prompt text and weight calculation) ──
NEURO_CRITERIA = [
    ("breakthrough", "突破性(Breakthrough)", 0.3, "是否颠覆范式或开辟新领域（9-10分=里程碑，如首次发现；7-8分=重要进展）"),
    ("methodology", "方法学创新(Methodology)", 0.2, "技术原创性和严谨性（全新技术9-10分，改进应用7-8分）"),
    ("evidence", "证据强度(Evidence)", 0.2, "实验设计的严谨性和结论的可靠性（多模态验证加分）"),
    ("contribution", "领域贡献度(Contribution)", 0.2, "对神经科学理论或实践的直接贡献度"),
    ("accessibility", "可传播性(Accessibility)", 0.1, "非专业人士能否感知其价值（概念清晰度）"),
]

GENERAL_CRITERIA = [
    ("Importance", "重要性(Importance)", 0.3, "该发现在其本领域的影响力（9-10分=诺贝尔奖级，7-8分=重要进展）"),
    ("Transferability", "迁移性(Transferability)", 0.3, "对神经科学等其他领域的应用潜力（技术/方法/理论可迁移性）"),
    ("Inspiration", "启发性(Inspiration)", 0.2, "能为神经科学等其他领域提供新视角或解决长期难题的可能性"),
    ("Timeliness", "时效性(Timeliness)", 0.1, "是否处于当前科技热点（如AI革命、基因编辑突破期）"),
    ("Accessibility", "可传播性(Accessibility)", 0.1, "领域外读者能否理解其重要性"),
]


def _build_score_prompt(criteria: list) -> str:
    """Generate scoring criteria description from constant tuples."""
    lines = ["评分标准："]
    for i, (key, name, weight, desc) in enumerate(criteria, 1):
        lines.append(f"{i}. {name}: {desc}（权重{int(weight*100)}%）")
    lines.append("")
    lines.append("权重说明：" + "，".join(
        f"{name}{int(weight*100)}%" for _, name, weight, _ in criteria
    ))
    return "\n".join(lines)


def _build_json_example(criteria: list) -> str:
    """Generate a clean JSON example for the prompt."""
    example = {
        "scores": {key: "0.0-10.0" for key, _, _, _ in criteria},
        "confidence": "0-10",
        "feature_angle": "面向读者的核心卖点（一句话）",
        "key_strength": "最大亮点",
        "key_limitation": "主要局限或不足",
        "target_audience": "最适合的读者群体",
    }
    return json.dumps(example, ensure_ascii=False, indent=2)


# ── Pydantic response models ──

class Response1(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True, use_enum_values=True)
    title_zh: str = Field(description="标题的中文翻译")
    domain: DomainType = Field(description="顶层域判断：核心域 / 域外高影响 / 域外局限")
    confidence: float = Field(ge=0, le=10, description="对分类结果的置信度，0-10分")
    cross_domain_potential: float = Field(
        default=0.0, ge=0, le=10,
        description="如果是域外高影响，说明其对神经科学等的跨界价值（0-10分）；核心域可填0"
    )
    # 核心域时必填，域外时为null
    primary_category: Optional[DomainCategory] = Field(
        default=None,
        description='''核心域必填：具体的神经科学子领域，可选基础类别：
- 认知神经科学
- 系统与环路神经科学
- 分子与细胞神经科学
- 发育神经科学
- 感觉与运动神经科学
- 计算与理论神经科学
- 临床与转化神经科学
- 社会与情感神经科学
- 方法学'''
    )
    reasoning: str = Field(min_length=5, max_length=200, description="一句话理由，解释分类依据")

    @model_validator(mode='after')
    def validate_logic(self):
        if self.domain == DomainType.CORE:
            if self.primary_category is None:
                raise ValueError("核心域必须提供 primary_category")
        elif self.domain == DomainType.CROSS_HIGH_IMPACT:
            self.primary_category = None
        else:  # CROSS_LIMITED
            self.primary_category = None
        return self


class NeuroScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    breakthrough: float = Field(ge=0.0, le=10.0, description="突破性/创新性评分")
    methodology: float = Field(ge=0.0, le=10.0, description="方法论严谨性评分")
    evidence: float = Field(ge=0.0, le=10.0, description="证据充分性评分")
    contribution: float = Field(ge=0.0, le=10.0, description="学术贡献度评分")
    accessibility: float = Field(ge=0.0, le=10.0, description="可读性/易理解性评分")


class GeneralScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Importance: float = Field(ge=0.0, le=10.0, description="该发现在其本领域的影响力（9-10分=诺贝尔奖级，7-8分=重要进展）")
    Transferability: float = Field(ge=0.0, le=10.0, description="对神经科学等其他领域的应用潜力（技术/方法/理论可迁移性）")
    Inspiration: float = Field(ge=0.0, le=10.0, description="能为神经科学等其他领域提供新视角或解决长期难题的可能性")
    Timeliness: float = Field(ge=0.0, le=10.0, description="是否处于当前科技热点（如AI革命、基因编辑突破期）")
    Accessibility: float = Field(ge=0.0, le=10.0, description="领域外读者能否理解其重要性")


class Response2Neuro(BaseModel):
    model_config = ConfigDict(extra="allow")
    scores: NeuroScores = Field(description="各维度评分（0.0-10.0）")
    confidence: int = Field(ge=0, le=10, description="评估置信度（0-10整数）")
    feature_angle: str = Field(min_length=1, description="面向读者的核心卖点（一句话）")
    key_strength: str = Field(min_length=1, description="最大亮点")
    key_limitation: str = Field(min_length=1, description="主要局限或不足")
    target_audience: str = Field(min_length=1, description="最适合的读者群体")


class Response2General(BaseModel):
    model_config = ConfigDict(extra="allow")
    scores: GeneralScores = Field(description="各维度评分（0.0-10.0）")
    confidence: int = Field(ge=0, le=10, description="评估置信度（0-10整数）")
    feature_angle: str = Field(min_length=1, description="面向读者的核心卖点（一句话）")
    key_strength: str = Field(min_length=1, description="最大亮点")
    key_limitation: str = Field(min_length=1, description="主要局限或不足")
    target_audience: str = Field(min_length=1, description="最适合的读者群体")


class ZeroScores(BaseModel):
    """All-zero scores for skipped / low-relevance papers."""
    model_config = ConfigDict(extra="forbid")
    breakthrough: float = 0.0
    methodology: float = 0.0
    evidence: float = 0.0
    contribution: float = 0.0
    accessibility: float = 0.0
    Importance: float = 0.0
    Transferability: float = 0.0
    Inspiration: float = 0.0
    Timeliness: float = 0.0
    Accessibility: float = 0.0


class Response2Skipped(BaseModel):
    """Fixed response for CROSS_LIMITED papers that skip Stage-2 scoring."""
    model_config = ConfigDict(extra="allow")
    scores: ZeroScores = Field(default_factory=ZeroScores)
    confidence: int = 0
    feature_angle: str = "无"
    key_strength: str = "无"
    key_limitation: str = "无"
    target_audience: str = "无"


class Response3(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    final_categories: List[str] = Field(
        min_length=1, max_length=3,
        description="""最终分类：1-2个最匹配的类别，主要类别在前。
可选基础类别：
- 认知神经科学
- 系统与环路神经科学
- 分子与细胞神经科学
- 发育神经科学
- 感觉与运动神经科学
- 计算与理论神经科学
- 临床与转化神经科学
- 社会与情感神经科学
- 方法学
- 域外高影响

可组合使用，如：["认知神经科学", "方法学"]"""
    )

    cross_tags: List[str] = Field(
        min_length=1, max_length=10,
        description="""交叉标签：从以下维度自由提取关键标签，每个标签2-6字为宜，最多6个标签。
示例维度：
- 方法学：fMRI、单细胞测序、光遗传学、计算建模、机器学习、行为学
- 物种：人类、小鼠、非人灵长类、果蝇、类脑器官
- 脑区：前额叶、海马、视觉皮层、全脑、边缘系统
- 技术：神经影像、电生理、光学成像、基因编辑
- 疾病/表型：阿尔茨海默、抑郁、成瘾、可塑性、记忆
- 其他：跨物种比较、脑机接口、神经伦理

示例：["fMRI", "人类", "前额叶", "工作记忆", "计算建模"]"""
    )

    recommendation_text: str = Field(
        min_length=10, max_length=500,
        description="推荐语：200字以内，面向神经科学读者，突出核心创新价值与意义"
    )

    crossover_value: Optional[str] = Field(
        default=None,
        min_length=10, max_length=300,
        description="跨界价值说明：当类别包含'域外高影响'时必填，解释为何神经科学读者应关注此研究"
    )

    editor_note: Optional[str] = Field(
        default=None,
        max_length=200,
        description="编辑备注：内部工作参考，选填"
    )

    @model_validator(mode='after')
    def validate_crossover_logic(self):
        has_external = any("域外" in cat for cat in self.final_categories)

        if has_external and not self.crossover_value:
            raise ValueError("包含'域外'类别的论文必须提供 crossover_value")

        if not has_external and self.crossover_value:
            self.crossover_value = None

        return self


class PromptGenerator:
    """论文分析器，实现三级筛选流程"""

    SYSTEM_PROMPT = (
        "你是神经科学文献专家，熟悉Nature/Science/Cell等顶刊标准。\n"
        "你的任务是严格筛选和评分论文，确保只有高质量、高相关性的研究被推荐给专业的神经科学读者和计算、系统生物学家。\n"
        "输出必须是合法的JSON格式，不要有任何额外解释。\n"
    )

    def __init__(self):
        self.recommendation_tier = ["头条推荐", "深度解读", "简要提及", "不推送"]

    def _generate_paper_id(self, paper: Paper) -> str:
        """生成论文唯一ID"""
        content = f"{paper.title}{paper.date}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _recommendation_level(self, scores: Dict, domain: str) -> tuple[float, str]:
        if domain == "核心域":
            if "breakthrough" in scores:
                average_score = sum(
                    weight * scores.get(key, 0) for key, _, weight, _ in NEURO_CRITERIA
                )
            else:
                average_score = 0
            if average_score > 9:
                return average_score, self.recommendation_tier[0]
            elif average_score > 7:
                return average_score, self.recommendation_tier[1]
            else:
                return average_score, self.recommendation_tier[2]
        else:
            if "Importance" in scores:
                average_score = sum(
                    weight * scores.get(key, 0) for key, _, weight, _ in GENERAL_CRITERIA
                )
            else:
                average_score = 0
            if average_score > 9:
                return average_score, self.recommendation_tier[0]
            elif average_score > 7:
                return average_score, self.recommendation_tier[2]
            else:
                return average_score, self.recommendation_tier[3]

    def _stage1_domain_classification(self, paper: Paper) -> str:
        """第一关：领域分类（Neuroscience/Others） 使用轻量级判断，节省成本"""

        example = {
            "title_zh": "标题的中文翻译",
            "domain": "核心域 | 域外高影响 | 域外局限",
            "confidence": "0.0-10.0",
            "primary_category": "如果核心域，必须从上述预定义的神经科学子领域中选择一个",
            "reasoning": "一句话理由",
            "cross_domain_potential": "如果是域外，说明其价值（0-10分）",
        }

        prompt = f"""分析以下论文与神经科学的相关性：

标题：{paper.title}
期刊：{paper.journal}
摘要：{paper.abstract[:800]}...

请执行以下操作：
1. 是否和脑科学、神经科学、认知科学、计算神经科学、系统生物学非常相关？如果是，文章属于"核心域"，跳过第2条，否则判断第2条。
2. 如果不是上述内容直接相关，但文章意义重大，未来可以影响人类社会或未来可能对神经科学有推动作用，文章属于"域外高影响"，如果文章只在领域内重要，属于"域外局限"。请做出判断并在下方用json格式输出。
3. 无论1，2的判断结果，将标题翻译为中文。

重要提示：primary_category 字段只能从以下预定义的神经科学子领域中选择：
- 认知神经科学
- 系统与环路神经科学
- 分子与细胞神经科学
- 发育神经科学
- 感觉与运动神经科学
- 计算与理论神经科学
- 临床与转化神经科学
- 社会与情感神经科学
- 方法学

输出JSON格式：
{json.dumps(example, ensure_ascii=False, indent=2)}"""
        return prompt

    def _stage2_strict_scoring(self, paper: Paper, domain_result: Dict) -> str:
        """第二关：严苛评分（仅核心域和域外高影响通过）"""

        domain = domain_result.get("domain", "")

        if domain == "域外局限":
            return ''

        # 提取大牛作者信息作为评分参考
        raw_data = getattr(paper, 'raw_data', {})
        senior_info_text = ""

        senior_authors = raw_data.get('senior_authors', [])
        if senior_authors:
            senior_info_text = "\n【作者影响力参考】\n该论文包含以下知名学者（可作为质量参考，但不直接决定评分）：\n"
            for sr in senior_authors:
                name = sr.get('name', '')
                h_idx = sr.get('h_index', 'N/A')
                cites = sr.get('citations', 'N/A')
                senior_info_text += f"- {name}: h-index={h_idx}, 总引用={cites}\n"
            senior_info_text += "\n"

        # ── 综述/观点类文章适配 ──
        REVIEW_INTRO = (
            "\n【文章类型判断】\n"
            "请先判断该文章是原创研究（original research）还是综述/观点类文章（Review, Perspective, Commentary, Opinion, Insight, Primer）。\n"
            "如果是综述/观点类文章，请改用以下「综述专用评分标准」，并将得分映射到相同的 JSON 键名上（见下方映射说明）。\n"
        )

        REVIEW_CRITERIA_TEXT = """综述专用评分标准（仅当文章为 Review / Perspective / Commentary / Opinion / Insight / Primer 时使用）：
1. 全面性(Comprehensiveness): 是否系统覆盖了该领域的关键进展、争议与空白（9-10分=里程碑式综述；7-8分=扎实全面）
2. 批判性(Criticality): 是否超越简单罗列，提供了独到的整合、批判性评价或新框架（9-10分=提出新范式；7-8分=有洞见的整合）
3. 时效性(Timeliness): 是否涵盖最新文献和当前热点，引用是否及时（前沿性）
4. 指导性(Guidance): 对该领域未来方向、方法学或转化应用是否有明确且可行的建议
5. 可传播性(Accessibility): 非该子领域读者能否从中受益，写作是否清晰

权重：全面性25%，批判性25%，时效性20%，指导性20%，可传播性10%

JSON 键名映射（必须严格遵守，以便下游程序统一计算）：
- 核心域综述：breakthrough=全面性, methodology=批判性, evidence=时效性, contribution=指导性, accessibility=可传播性
- 域外综述：Importance=全面性, Transferability=批判性, Inspiration=指导性, Timeliness=时效性, Accessibility=可传播性
"""

        if domain == "域外高影响":
            original_scoring = _build_score_prompt(GENERAL_CRITERIA)
            json_criteria = _build_json_example(GENERAL_CRITERIA)
        else:
            original_scoring = _build_score_prompt(NEURO_CRITERIA)
            json_criteria = _build_json_example(NEURO_CRITERIA)

        prompt = f"""对以下论文进行顶刊级严苛评分：

标题：{paper.title}
作者：{', '.join(paper.authors[:5]) + ('' if len(paper.authors) <= 5 else 'et. al.')}
期刊：{paper.journal}
日期：{paper.date}
{senior_info_text}
摘要：{paper.abstract}
{REVIEW_INTRO}
{REVIEW_CRITERIA_TEXT}

{original_scoring}

输出JSON格式：
{json_criteria}"""

        return prompt

    def _stage3_detailed_analysis(self, paper: Paper, scores: float, domain: str, primary_category: str) -> str:
        """第三关：详细分析（仅对≥7.0分的文章） 生成推荐语、标签等"""

        total_score = scores
        if total_score < 7.0:
            return ''

        example = {
            "final_categories": ["主要类别", "次要类别"],
            "cross_tags": ["标签1", "标签2", "标签3"],
            "recommendation_text": "推荐语",
            "crossover_value": "跨界价值说明（如适用）",
            "editor_note": "编辑备注（选填）",
        }

        prompt = f"""为以下论文生成详细的分析内容：

标题：{paper.title}
摘要：{paper.abstract[:600]}...
领域：{domain}
主类别：{primary_category}
得分：{total_score}/10

任务：
1. 确定最终分类（从8个核心类别或域外高影响中选择最匹配的1-2个）
2. 生成交叉标签（方法学、物种、脑区、技术）
3. 撰写推荐语（大约100-300字，面向神经科学领域读者，突出价值）
4. 如果是域外高影响，撰写"跨界价值说明"（为何领域外读者应该关注）

输出JSON：
{json.dumps(example, ensure_ascii=False, indent=2)}"""
        return prompt
