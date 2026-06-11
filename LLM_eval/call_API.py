import json
from openai import OpenAI
import os
from StructuredPrompt import PromptGenerator, Response1, Response2General, Response2Neuro, Response2Skipped, Response3
from util import Paper, PaperResult, DomainType
from pydantic import BaseModel, ValidationError

class LLM_process:
    def __init__(self, api_key:str, base_url:str ="https://api.deepseek.com", model="deepseek-v4-flash", thinking:bool=False, provider: str | None = None) -> None:
        """
        dpsk: https://api.deepseek.com
            models : deepseek-v4-flash, deepseek-v4-pro
        aliyuncs: https://dashscope.aliyuncs.com/compatible-mode/v1
            models: check their website, including qwen3.7-plus
        """
        self.api_key :str = api_key # type: ignore # 
        self.base_url:str = base_url
        self.client = OpenAI(
            api_key=self.api_key, 
            base_url= self.base_url
            )
        self.model = model
        self.thinking = thinking
        self.provider = (provider or self._detect_provider(base_url)).lower()

    @staticmethod
    def _detect_provider(base_url: str) -> str:
        base_url = (base_url or "").lower()
        if "deepseek" in base_url:
            return "deepseek"
        if "dashscope" in base_url or "aliyun" in base_url:
            return "aliyuncs"
        return "openai_compatible"

    @staticmethod
    def _extract_json_object(content: str) -> dict:
        """
        Parse a JSON object from model content.
        DeepSeek JSON mode should return valid JSON, but this also tolerates
        accidental fenced code blocks.
        """
        if not content or not content.strip():
            raise ValueError("empty model content")
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`").strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start:end + 1])
            raise

    @staticmethod
    def _json_schema_hint(response_model: type[BaseModel]) -> str:
        schema = response_model.model_json_schema()
        return json.dumps(schema, ensure_ascii=False, indent=2)

    def _completion_with_provider_schema(self, SystemPrompt: str, UserPrompt: str, response_format: type[BaseModel]):
        completion = self.client.chat.completions.parse(
            model = self.model,
            messages=[
                    {"role": "system", "content": SystemPrompt},
                    {"role": "user", "content": UserPrompt},
                ],
            extra_body={"enable_thinking":self.thinking},
            response_format=response_format,
            )
        result = completion.choices[0].message.parsed  # 类型安全的解析结果
        return result

    def _completion_with_json_mode(self, SystemPrompt: str, UserPrompt: str, response_format: type[BaseModel]):
        schema_hint = self._json_schema_hint(response_format)
        system_prompt = (
            f"{SystemPrompt}\n\n"
            "You must output only one valid JSON object. Do not output Markdown, code fences, or explanations.\n"
            "The JSON object must satisfy this JSON Schema. If a field is optional and unknown, use null or an empty list as appropriate.\n"
            f"{schema_hint}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": UserPrompt},
        ]
        last_error = None

        for attempt in range(3):
            kwargs = {
                "model": self.model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "max_tokens": 4096,
            }
            if self.thinking:
                kwargs["extra_body"] = {"enable_thinking": self.thinking}
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            try:
                parsed_json = self._extract_json_object(content)
                return response_format.model_validate(parsed_json)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                messages.append({"role": "assistant", "content": content or ""})
                messages.append({
                    "role": "user",
                    "content": (
                        "The previous response was not valid for the required JSON schema. "
                        f"Validation/parsing error: {str(exc)[:1200]}\n"
                        "Return a corrected JSON object only."
                    ),
                })

        raise RuntimeError(f"Failed to get valid JSON after retries: {last_error}")

    def completion(self, SystemPrompt:str, UserPrompt:str, response_format:type):
        if self.provider in {"aliyuncs", "dashscope"}:
            return self._completion_with_provider_schema(SystemPrompt, UserPrompt, response_format)
        return self._completion_with_json_mode(SystemPrompt, UserPrompt, response_format)


class ArticleProcess:
    def __init__(self, article_info:dict) -> None:
        self.paper = Paper.from_json(article_info)
        self.PaperAnalysis = None
        # print(self.paper)
    
    def process(self, PaperPromptGenerator:PromptGenerator, LLM_api:LLM_process) -> PaperResult:

        self.paperid = PaperPromptGenerator._generate_paper_id(paper=self.paper)

        # first, tell the category of the following article.
        # =================================================================================================
        prompt1 = PaperPromptGenerator._stage1_domain_classification(self.paper)
        result_json1 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt1, Response1)
        assert result_json1 is not None # the first result should not be empty, by any means.

        # 直接访问 Pydantic 模型对象的属性
        self.title_zh = result_json1.title_zh

        self.domain = result_json1.domain
        self.domain_confidence = result_json1.confidence
        self.primary_category = result_json1.primary_category
        self.domain_reasoning = result_json1.reasoning
        self.cross_domain_potential = result_json1.cross_domain_potential

        # 将 Pydantic 模型对象转换为字典传递给 _stage2_strict_scoring 方法
        prompt2 = PaperPromptGenerator._stage2_strict_scoring(paper=self.paper, domain_result=result_json1.model_dump())
        if self.domain == DomainType.CORE and prompt2:
            result_json2 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt2, Response2Neuro)
        elif self.domain == DomainType.CROSS_HIGH_IMPACT and prompt2:
            result_json2 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt2, Response2General)
        elif self.domain == DomainType.CROSS_LIMITED and not prompt2:
            result_json2 = Response2Skipped()
        else:
            raise RuntimeError(f'The type of research is {self.domain}, but the prompt is not empty = {prompt2}')
        assert result_json2 is not None

        # 直接访问 Pydantic 模型对象的属性
        self.scores = result_json2.scores.model_dump() if hasattr(result_json2, 'scores') else result_json2.get('scores', None)
        self.scoring_confidence = result_json2.confidence if hasattr(result_json2, 'confidence') else result_json2.get('confidence', None)
        self.feature_angle = result_json2.feature_angle if hasattr(result_json2, 'feature_angle') else result_json2.get("feature_angle", '')
        self.key_strength = result_json2.key_strength if hasattr(result_json2, 'key_strength') else result_json2.get('key_strength', None)
        self.key_limitation = result_json2.key_limitation if hasattr(result_json2, 'key_limitation') else result_json2.get('key_limitation', None)
        self.target_audience = result_json2.target_audience if hasattr(result_json2, 'target_audience') else result_json2.get('target_audience', None)


        self.article_scores, self.recommendation_level = PaperPromptGenerator._recommendation_level(scores=self.scores, domain=self.domain) # type: ignore 
        prompt3 = PaperPromptGenerator._stage3_detailed_analysis(self.paper, scores=self.article_scores, domain=self.domain, primary_category=self.primary_category) # type: ignore
        
        if prompt3: 
            result_json3 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt3, Response3)
            assert result_json3 is not None

            # 直接访问 Pydantic 模型对象的属性
            self.final_categories     = result_json3.final_categories
            self.cross_tags           = result_json3.cross_tags
            self.recommendation_text  = result_json3.recommendation_text
            self.crossover_value      = result_json3.crossover_value
            self.editor_note          = result_json3.editor_note
        else:
            self.final_categories     = [] # result_json3.get("final_categories", None)
            self.cross_tags           = [] # result_json3.get("cross_tags", None)
            self.recommendation_text  = '' # result_json3.get("recommendation_text", None)
            self.crossover_value      = '' # result_json3.get("crossover_value", None)
            self.editor_note          = '' # result_json3.get("editor_note", None)

        AnalyzeResult = PaperResult(
            paper=self.paper,
            title_zh=self.title_zh,
            paper_id=self.paperid,
            domain= self.domain,
            primary_category=self.primary_category,
            secondary_category=self.final_categories,
            cross_tags=self.cross_tags,
            scores=self.scores, # type: ignore 
            total_score=self.article_scores,
            recommendation_tier=self.recommendation_level,
            recommendation_text=self.recommendation_text,
            confidence=self.domain_confidence,
            reasoning=self.domain_reasoning,
            feature_angle=self.feature_angle,
            model_used=LLM_api.model,
            key_strength=self.key_strength,
            key_limitation=self.key_limitation,
            target_audience=self.target_audience,
            crossover_value=self.crossover_value,
            editor_note=self.editor_note,
            cross_domain_potential=self.cross_domain_potential,
        )

        return AnalyzeResult
        

def main():
    pass

if __name__ == "__main__":
    main()
