# core/llm_base.py
from abc import ABC, abstractmethod

class BaseLLM(ABC):
    @abstractmethod
    def ideation(self, user_base_idea: str, num_variations: int) -> list[dict]:
        """构思因子，返回字典列表"""
        pass

    @abstractmethod
    def code_generation(self, factor_description: str, factor_name: str) -> str:
        """生成代码，返回代码字符串"""
        pass