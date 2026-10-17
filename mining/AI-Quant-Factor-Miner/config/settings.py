# config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# ===========================
# 1. 核心模型配置
# ===========================
# 切换当前使用的提供商: 'deepseek' 'gemini' 'kimi' 'qwen' 'zhipu'
# 构思用的模型 (大脑)
ACTIVE_IDEATION_PROVIDER = 'qwen' 

# 写代码用的模型 (手) 
ACTIVE_CODING_PROVIDER = 'kimi'

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KIMI_API_KEY = os.getenv("KIMI_API_KEY")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")   
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")    

MODEL_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "ideation_model": "deepseek-reasoner",
        "coding_model": "glm-4.7",
        "temperature_ideation": 0.7,
        "temperature_coding": 0.0,
    },
    # "gemini": {
    #     "ideation_model": "gemini-3-pro-preview",
    #     "coding_model": "gemini-2.5-flash",
    #     "temperature_ideation": 0.7,
    #     "temperature_coding": 0.0,
    # },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "ideation_model": "kimi-k2-thinking-turbo", 
        "coding_model": "moonshot-v1-32k",
        "temperature_ideation": 0.7,
        "temperature_coding": 0.0,
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "ideation_model": "qwen-max", 
        "coding_model": "qwen-max",  
        "temperature_ideation": 0.7,
        "temperature_coding": 0.0,
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "ideation_model": "glm-4.7",
        "coding_model": "glm-4.7",      
        "temperature_ideation": 0.7,
        "temperature_coding": 0.0,
    }
}

# ===========================
# 2. 数据与字段定义
# ===========================
# 基础根目录
BASE_OUTPUT_DIR = r"D:\框架\QuantFactorAI\output\correlation"
DATA_PATH_STOCK = r"D:\框架\QuantFactorAI\data\data.parquet"
DATA_PATH_INDEX = r"D:\框架\QuantFactorAI\data\index.parquet"

STOCK_COLUMNS_DESC = """
'TradingDay', 'SecuCode', 'PrevClosePrice', 'OpenPrice', 'HighPrice', 'LowPrice',
'ClosePrice', 'TurnOverVolume', 'TurnOverValue', 'TurnOverRate', 'FloatMarketValue'
"""

INDEX_COLUMNS_DESC = """
'TradingDay', 'HS300', 'ZZ500', 'ZZ1000', 'SZ'
"""

REQUIRED_OUTPUT_COLS = ['SecuCode', 'TradingDay']
DEFAULT_NUM_VARIATIONS = 1

# ===========================
# 3. 因子挖掘任务清单
# ===========================
FACTOR_MINING_TASKS = [
    # momentum
    # {
    #    "idea": "rank(ts_argmax(signedpower(((ret < 0) ? stddev(ret, 20) : close), 2), 5)) - 0.5",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * rank(((sum(open, 5) * sum(ret, 5)) - delay((sum(open, 5) * sum(ret, 5)), 10)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(-1 * sign((close - delay(close, 7)) + delta(close, 7))) * (1 + rank(1 + sum(ret, 250)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "((delta(mean(close, 100), 100) / delay(close, 100)) <= 0.05) ? (-1 * (close - ts_min(close, 100))) : (-1 * delta(close, 3))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "rank((1 - rank(stddev(ret, 2) / stddev(ret, 5))) + (1 - rank(delta(close, 1))))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * ((rank(mean(delay(close, 5), 20)) * corr(close, vol, 2)) * rank(corr(sum(close, 5), sum(close, 20), 2)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(((delay(close, 20) - delay(close, 10))/10 - (delay(close, 10) - close)/10) < -0.1) ? 1 : (-1 * (close - delay(close, 1)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "ts_rank(vol/adv20, 20) * ts_rank(-1 * delta(close, 7), 8)",
    #    "num_variations": 1
    # },

    # reversion
    # {
    #    "idea": "-1 * ts_rank(rank(low), 9)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(0 < ts_min(delta(close, 1), 4)) ? delta(close, 1) : ((ts_max(delta(close, 1), 4) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "((-1 * ts_min(low, 5) + delay(ts_min(low, 5), 5)) * rank((sum(ret, 240) - sum(ret, 20)) / 220)) * ts_rank(vol, 5)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(close - open) / ((high - low) + 0.001)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "rank(open - (mean(vwap, 10))) * (-1 * abs(rank(close - vwap)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "((mean(close, 8) + stddev(close, 8)) < (mean(close, 2))) ? -1 : ((mean(close, 2) < (mean(close, 8) - stddev(close, 8))) ? 1 : ((vol/adv20 >= 1) ? 1 : -1))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "min(product(rank(rank(scale(log(sum(ts_min(rank(rank(-1 * rank(delta(close-1, 5)))), 2), 1))))), 1), 5) + ts_rank(delay(-1 * ret, 6), 5)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "scale(mean(close, 7) - close) + (20 * scale(corr(vwap, delay(close, 5), 230)))",
    #    "num_variations": 1
    # },

    # structure
    # {
    #    "idea": "(-1 * rank(open - delay(high, 1))) * rank(open - delay(close, 1)) * rank(open - delay(low, 1))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(-1 * rank(ts_rank(close, 10))) * rank(close / open)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * delta(((close - low) - (high - close)) / (close - low), 9)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(-1 * (low - close) * (open^5)) / ((low - high) * (close^5))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * (2 * scale(rank(((close - low) - (high - close)) / (high - low) * vol)) - scale(rank(ts_argmax(close, 10))))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(rank(ts_max((vwap - close), 3)) + rank(ts_min((vwap - close), 3))) * rank(delta(vol, 3))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(-1 * rank(ts_rank(close, 10))) * rank(delta(delta(close, 1), 1)) * rank(ts_rank(vol/adv20, 5))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "((mean(high, 20)) < high) ? (-1 * delta(high, 2)) : 0",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "scale(corr(adv20, low, 5) + (high + low)/2 - close), 230)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(ts_rank(vol, 32) * (1 - ts_rank(close + high - low, 16))) * (1 - ts_rank(ret, 32))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": " ((high * low)^0.5 - vwap)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "rank(vwap - close) / rank(vwap + close)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "((rank(1/close) * vol) / adv20) * ((high * rank(high - close)) / (mean(high, 5))) - rank(vwap - delay(vwap, 5))",
    #    "num_variations": 1
    # },

    # vol_liq
    # {
    #    "idea": "(adv20 < vol) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7))) : -1",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "sign(delta(vol, 1)) * (-1 * delta(close, 1))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * rank(stddev(abs(close - open), 5) + (close - open) + corr(close, open, 10))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * ts_max(rank(corr(rank(vol), rank(vwap), 5)), 5)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * corr(rank((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12))), rank(vol), 6)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "rank((-1 * ret * adv20 * vwap) * (high - close))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "((1.0 - rank(sign(close - delay(close, 1)) + sign(delay(close, 1) - delay(close, 2)) + sign(delay(close, 2) - delay(close, 3)))) * sum(vol, 5)) / sum(vol, 20)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "rank(rank(rank(decay_linear(-1 * rank(rank(delta(close, 10))), 10)))) + rank(-1 * delta(close, 3)) + sign(scale(corr(adv20, low, 12)))",
    #    "num_variations": 1
    # },


    # correlation
    # {
    #    "idea": "-1 * corr(rank(delta(log(vol), 2)), rank((close - open) / open), 6)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * corr(rank(open), rank(vol), 10)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * corr(open, vol, 10)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "rank(corr(delay(open - close, 1), close, 200)) + rank(open - close)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * corr(high, rank(vol), 5)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * rank(cov(rank(close), rank(vol), 5))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * sum(rank(corr(rank(high), rank(vol), 3)), 3)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * rank(cov(rank(high), rank(vol), 5))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * (delta(corr(high, vol, 5), 5) * rank(stddev(close, 20)))",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "-1 * ts_max(corr(ts_rank(vol, 5), ts_rank(high, 5), 5), 3)",
    #    "num_variations": 1
    # },
    # {
    #    "idea": "(0.5 < rank(sum(corr(rank(vol), rank(vwap), 6), 2) / 2.0)) ? -1 : 1",
    #    "num_variations": 1
    # },
]