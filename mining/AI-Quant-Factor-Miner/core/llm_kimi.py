# core/llm_kimi.py
from openai import OpenAI
from core.llm_base import BaseLLM
from config import settings
from utils.logger import logger
import json
import re

from core.prompts import (
    IDEATION_PROMPT_TEMPLATE,
    CODE_GEN_PROMPT_TEMPLATE,
    CODE_REFINE_PROMPT_TEMPLATE
)

class KimiLLM(BaseLLM):
    def __init__(self, api_key):
        self.client = OpenAI(
            api_key=api_key,
            base_url=settings.MODEL_CONFIG['kimi']['base_url']
        )
        self.config = settings.MODEL_CONFIG['kimi']

    def ideation(self, base_idea, num_variations=3):
        """Kimi 构思阶段"""
        prompt = IDEATION_PROMPT_TEMPLATE.format(
            num_variations=num_variations,
            stock_columns=settings.STOCK_COLUMNS_DESC,
            index_columns=settings.INDEX_COLUMNS_DESC,
            user_base_idea=base_idea
        )

        try:
            response = self.client.chat.completions.create(
                model=self.config['ideation_model'],
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config['temperature_ideation']
            )
            content = response.choices[0].message.content
            
            # 清洗 Markdown 标记 (Kimi 经常喜欢包 ```json ... ```)
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```", "", content)
            
            return json.loads(content)
        except Exception as e:
            logger.error(f"Ideation Error: {e}")
            return []

    def code_generation(self, factor_desc, factor_name):
        """Kimi 代码生成阶段"""
        prompt = CODE_GEN_PROMPT_TEMPLATE.format(
            factor_name=factor_name,
            stock_columns=settings.STOCK_COLUMNS_DESC,
            index_columns=settings.INDEX_COLUMNS_DESC,
            factor_description=factor_desc
        )

        try:
            response = self.client.chat.completions.create(
                model=self.config['coding_model'],
                messages=[
                    {"role": "system", "content": "You are a Python expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config['temperature_coding']
            )
            code = response.choices[0].message.content
            
            # 清洗代码块标记
            code = re.sub(r"```python\s*", "", code)
            code = re.sub(r"```", "", code)
            return code.strip()
        except Exception as e:
            logger.error(f"CodeGen Error: {e}")
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
            # 使用 coding_model 进行修复
            response = self.client.chat.completions.create(
                model=self.config['coding_model'],
                messages=[
                    {"role": "system", "content": "你是一个Python代码Debug专家。"},
                    {"role": "user", "content": prompt}
                ],
                stream=False,
                temperature=0.0 # 修复bug时温度要低，越精确越好
            )
            content = response.choices[0].message.content
            
            # 清洗代码
            content = re.sub(r"```python\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"```", "", content)
            return content.strip()
            
        except Exception as e:
            logger.error(f"代码修复失败: {e}")
            return None