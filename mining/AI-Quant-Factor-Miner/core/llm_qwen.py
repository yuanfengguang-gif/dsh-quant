from core.llm_kimi import KimiLLM
from config import settings
from openai import OpenAI

class QwenLLM(KimiLLM):
    """Qwen 完全兼容 OpenAI 格式，继承 Kimi 的逻辑但重置 Client"""
    def __init__(self, api_key):
        super().__init__(api_key)
        
        self.config = settings.MODEL_CONFIG['qwen']
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.config['base_url']
        )