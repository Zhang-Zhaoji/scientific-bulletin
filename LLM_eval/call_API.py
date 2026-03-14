import json
from openai import OpenAI
import os
from StructuredPrompt import PromptGenerator, Response1, Response2General, Response2Neuro, Response3, GeneralScores
from util import Paper, PaperResult, DomainType

class LLM_process:
    def __init__(self, base_url:str ="https://dashscope.aliyuncs.com/compatible-mode/v1", model="qwen-plus") -> None:
        self.api_key :str = os.getenv("DASHSCOPE_API_KEY"), # type: ignore # 
        self.base_url:str = base_url
        self.client = OpenAI(
            api_key=self.api_key, 
            base_url= self.base_url
            )
        self.model = model
    
    def completion(self, SystemPrompt, UserPrompt, response_format):
        completion = self.client.chat.completions.parse(
            model = self.model,
            messages=[
                    {"role": "system", "content": SystemPrompt},
                    {"role": "user", "content": UserPrompt},
                ],
            response_format=response_format,
            )
        result = completion.choices[0].message.parsed  # 类型安全的解析结果
        return result


class ArticleProcess:
    def __init__(self, article_info:dict) -> None:
        self.paper = Paper.from_json(article_info)
        self.PaperAnalysis = None
        print(self.paper)
    
    def process(self, PaperPromptGenerator:PromptGenerator, LLM_api:LLM_process) -> PaperResult:

        self.paperid = PaperPromptGenerator._generate_paper_id(paper=self.paper)

        # first, tell the category of the following article.
        # =================================================================================================
        prompt1 = PaperPromptGenerator._stage1_domain_classification(self.paper)
        result_json1 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt1, Response1)
        assert result_json1 is not None # the first result should not be empty, by any means.

        self.domain = result_json1.get("domain", None)
        self.domain_confidence = result_json1.get("confidence", None)
        self.primary_category = result_json1.get("primary_category", None)
        self.domain_reasoning = result_json1.get("reasoning", None)

        prompt2 = PaperPromptGenerator._stage2_strict_scoring(paper=self.paper, domain_result=result_json1)
        if self.domain == DomainType.CORE and prompt2:
            result_json2 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt2, Response2Neuro)
        elif self.domain == DomainType.CROSS_HIGH_IMPACT and prompt2:
            result_json2 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt2, Response2General)
        elif self.domain == DomainType.CROSS_LIMITED and not prompt2:
            scores = GeneralScores(Importance=0.,Transferability=0.,Inspiration=0.,Timeliness=0., Accessibility=0.)
            result_json2 = Response2General(scores = scores, confidence=0, feature_angle='', key_strength='', key_limitation='', target_audience='')
            result_json2 = result_json2.model_dump()
        else:
            raise RuntimeError(f'The type of research is {self.domain}, but the prompt is not empty = {prompt2}')
        assert result_json2 is not None

        self.scores = result_json2.get('scores', None)
        self.scoring_confidence = result_json2.get('confidence', None)
        self.feature_angle = result_json2.get("feature_angle", '')
        self.key_strength = result_json2.get('key_strength', None)
        self.key_limitation = result_json2.get('key_limitation', None)
        self.target_audience = result_json2.get('target_audience',None)


        self.article_scores, self.recommendation_level = PaperPromptGenerator._recommendation_level(scores=self.scores, domain=self.domain) # type: ignore 
        prompt3 = PaperPromptGenerator._stage3_detailed_analysis(self.paper, scores=self.article_scores, domain=self.domain, primary_category=self.primary_category) # type: ignore
        
        if prompt3: 
            result_json3 = LLM_api.completion(PaperPromptGenerator.SYSTEM_PROMPT, prompt3, Response3)
            assert result_json3 is not None

            self.final_categories     = result_json3.get("final_categories", None)
            self.cross_tags           = result_json3.get("cross_tags", None)
            self.recommendation_text  = result_json3.get("recommendation_text", None)
            self.crossover_value      = result_json3.get("crossover_value", None)
            self.editor_note          = result_json3.get("editor_note", None)
        else:
            self.final_categories     = None # result_json3.get("final_categories", None)
            self.cross_tags           = [] # result_json3.get("cross_tags", None)
            self.recommendation_text  = None # result_json3.get("recommendation_text", None)
            self.crossover_value      = None # result_json3.get("crossover_value", None)
            self.editor_note          = None # result_json3.get("editor_note", None)

        AnalyzeResult = PaperResult(
            paper_id=self.paperid,
            domain= self.domain,
            primary_category=self.primary_category,
            secondary_category=self.final_categories,
            cross_tags=self.cross_tags,
            scores=self.scores, # type: ignore 
            total_score=self.article_scores,
            recommendation_tier=self.recommendation_level,
            confidence=self.domain_confidence,
            reasoning=self.domain_reasoning,
            feature_angle=self.feature_angle,
            model_used=LLM_api.model
        )

        return AnalyzeResult
        

def main():
    pass

if __name__ == "__main__":
    main()