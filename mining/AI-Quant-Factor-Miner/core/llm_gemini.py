# core/llm_gemini.py
import google.generativeai as genai
import json
from core.llm_base import BaseLLM
from core.prompts import IDEATION_PROMPT_TEMPLATE, CODE_GEN_PROMPT_TEMPLATE, CODE_REFINE_PROMPT_TEMPLATE
from config import settings
from utils.logger import logger

class GeminiLLM(BaseLLM):
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.config = settings.MODEL_CONFIG['gemini']
        
    def ideation(self, user_base_idea: str, num_variations: int) -> list[dict]:
        prompt = IDEATION_PROMPT_TEMPLATE.format(
            user_base_idea=user_base_idea, 
            num_variations=num_variations,
            stock_columns=settings.STOCK_COLUMNS_DESC,
            index_columns=settings.INDEX_COLUMNS_DESC
        )
        
        try:
            model = genai.GenerativeModel(
                model_name=self.config['ideation_model'],
                system_instruction="你是一个量化因子构思专家，只输出JSON。",
                generation_config={
                    "response_mime_type": "application/json", 
                    "temperature": self.config['temperature_ideation']
                }
            )
            
            response = model.generate_content(prompt)
            return json.loads(response.text)
            
        except Exception as e:
            logger.error(f"Gemini 构思失败: {e}")
            return None

    def code_generation(self, factor_description: str, factor_name: str) -> str:
        prompt = CODE_GEN_PROMPT_TEMPLATE.format(
            factor_description=factor_description, 
            factor_name=factor_name,
            stock_columns=settings.STOCK_COLUMNS_DESC,
            index_columns=settings.INDEX_COLUMNS_DESC
        )
        
        try:
            model = genai.GenerativeModel(
                model_name=self.config['coding_model'],
                system_instruction="你是一个量化因子代码生成器。",
                generation_config={
                    "response_mime_type": "text/plain", 
                    "temperature": self.config['temperature_coding']
                }
            )
            
            response = model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini 代码生成失败: {e}")
            return None
            
    def code_refinement(self, old_code: str, error_msg: str, factor_name: str, formula: str) -> str:
        prompt = CODE_REFINE_PROMPT_TEMPLATE.format(
            factor_name=factor_name,
            factor_formula=formula, 
            error_type="Runtime Error",
            old_code=old_code,
            error_message=error_msg,
            stock_columns=settings.STOCK_COLUMNS_DESC,
            index_columns=settings.INDEX_COLUMNS_DESC
        )
        
        try:

            response = self.client.chat.completions.create(
                model=self.config['coding_model'],
                messages=[
                    {"role": "system", "content": "你是一个Python代码Debug专家。"},
                    {"role": "user", "content": prompt}
                ],
                stream=False,
                temperature=0.0
            )
            content = response.choices[0].message.content
            
            content = re.sub(r"```python\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"```", "", content)
            return content.strip()
            
        except Exception as e:
            logger.error(f"代码修复失败: {e}")
            return None