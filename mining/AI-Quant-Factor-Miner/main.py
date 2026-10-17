# main.py
import os
import sys
import time
import warnings
from datetime import datetime

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import settings

from data_loader.loader import DataLoader 
from utils.logger import logger

# LLM 核心类
from core.llm_deepseek import DeepSeekLLM
from core.llm_gemini import GeminiLLM
from core.llm_kimi import KimiLLM
from core.llm_qwen import QwenLLM
from core.llm_zhipu import ZhipuLLM

# 引擎模块
from engine.code_manager import CodeManager
from engine.executor import Executor

from engine.metadata_recorder import MetadataRecorder 

warnings.filterwarnings("ignore") 


def get_llm_instance(provider_name):
    """
    工厂模式：根据传入的名称返回对应的 LLM 实例
    :param provider_name: 'deepseek', 'zhipu', 'qwen', etc.
    """
    p_name = provider_name.lower()
    
    if p_name == 'deepseek':
        # 构思大脑 (Brain)
        return DeepSeekLLM(api_key=settings.DEEPSEEK_API_KEY)
    elif p_name == 'gemini':
        return GeminiLLM(api_key=settings.GEMINI_API_KEY)
    elif p_name == 'kimi':
        return KimiLLM(api_key=settings.KIMI_API_KEY)
    elif p_name == 'qwen':
        return QwenLLM(api_key=settings.QWEN_API_KEY)    
    elif p_name == 'zhipu':
        # 代码写手 (Hand)
        return ZhipuLLM(api_key=settings.ZHIPU_API_KEY)
    else:
        raise ValueError(f"未知的模型类型: {provider_name}")

def process_single_factor_idea(llm_coding, executor, idea_dict, code_output_dir, factor_output_dir, recorder, seed_idea, provider_name):
    """
    处理单个因子：生成 -> 保存 -> 执行 -> (自动修复循环) -> 记录
    :param llm_coding: 专门用于写代码的 LLM 实例 (如 Zhipu)
    :param provider_name: 记录日志用的模型名称
    """
    # 1. 提取元数据
    original_factor_name = idea_dict.get("factor_name")
    factor_desc = idea_dict.get("factor_description")
    factor_formula = idea_dict.get("factor_formula", "N/A")
    
    if not original_factor_name or not factor_desc:
        logger.warning("构思数据不完整，跳过。")
        return

    logger.info(f"--- 开始处理因子: {original_factor_name} (由 {provider_name} 编写) ---")
    
    # === 配置参数 ===
    MAX_RETRIES = 2 
    status = "Fail"
    
    # 状态变量
    current_code = None
    final_unique_name = None 
    final_code_path = "" 

    # === 阶段 1: 初次代码生成 ===
    try:
        input_prompt = f"Formula: {factor_formula}\nDescription: {factor_desc}"
        # 使用传入的 Coding LLM 生成代码
        current_code = llm_coding.code_generation(input_prompt, original_factor_name)
        
        if not current_code:
            logger.error(f"{original_factor_name} 代码生成返回为空。")
            recorder.add_record(provider_name, seed_idea, original_factor_name, factor_formula, factor_desc, "GenCode_Fail")
            return

    except Exception as e:
        logger.error(f"代码生成阶段发生异常: {e}")
        return

    # === 阶段 2: 执行与修复循环 ===
    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            logger.info(f">>> [第 {attempt} 次修复] 正在尝试修复 {original_factor_name} ...")
        
        # A. 保存代码 (自动重命名逻辑)
        target_filename = final_unique_name if attempt > 0 else None
        
        func, unique_name, code_path = CodeManager.save_and_load_function(
            code_string=current_code,
            factor_name=original_factor_name,   
            output_dir=code_output_dir,
            specific_name=target_filename       
        )
        
        # 锁定文件名
        if attempt == 0:
            final_unique_name = unique_name
            final_code_path = code_path
        
        # B. 语法检查
        if not func:
            logger.error(f"{final_unique_name} 加载失败 (语法错误)。")
            err_msg = "SyntaxError: The code could not be compiled."
            
            if attempt < MAX_RETRIES:
                # 使用 Coding LLM 进行修复
                new_code = llm_coding.code_refinement(current_code, err_msg, original_factor_name, factor_formula)
                if new_code:
                    current_code = new_code
                    continue
                else:
                    break
            else:
                break

        # C. 执行
        success, message = executor.run(func, final_unique_name, factor_output_dir)
        
        if success:
            status = "Success"
            logger.info(f"--- 因子 {final_unique_name} 执行成功 ---")
            break 
        else:
            logger.warning(f"执行失败: {message}")
            
            if attempt < MAX_RETRIES:
                logger.info("请求 AI 进行自我修正...")
                # 传入公式防止逻辑漂移
                refined_code = llm_coding.code_refinement(
                    old_code=current_code, 
                    error_msg=message, 
                    factor_name=original_factor_name,
                    formula=factor_formula 
                )
                
                if refined_code:
                    current_code = refined_code
                else:
                    logger.error("AI 放弃修复。")
                    break
            else:
                logger.error(f"已达到最大重试次数 ({MAX_RETRIES})。")

    # === 阶段 3: 清理与记录 ===
    
    # 清理垃圾文件
    if status != "Success" and final_code_path and os.path.exists(final_code_path):
        try:
            os.remove(final_code_path)
            logger.info(f"已清理无效文件: {final_code_path}")
        except Exception as e:
            logger.warning(f"清理失败: {e}")
            
    # 记录结果
    record_name = final_unique_name if final_unique_name else original_factor_name
    csv_code_path = final_code_path if status == "Success" else "Deleted"
    
    recorder.add_record(
        provider=provider_name, 
        seed_idea=seed_idea,
        factor_name=record_name, 
        formula=factor_formula,
        description=factor_desc,
        status=status,
        code_path=csv_code_path
    )


def main():
    ideation_provider = settings.ACTIVE_IDEATION_PROVIDER
    coding_provider = settings.ACTIVE_CODING_PROVIDER
    
    # 组合文件夹名称
    combo_name = f"{ideation_provider}"
    base_dir = os.path.join(settings.BASE_OUTPUT_DIR, combo_name)
    
    code_dir = os.path.join(base_dir, "codes")
    factor_dir = os.path.join(base_dir, "factors")
    
    os.makedirs(code_dir, exist_ok=True)
    os.makedirs(factor_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 初始化记录器 (使用 MetadataRecorder)
    recorder = MetadataRecorder(os.path.join(base_dir, f"factor_records_{timestamp_str}.csv"))

    logger.info("=== 启动双模型量化挖掘框架 ===")
    logger.info(f"构思大脑 (Brain): {ideation_provider}")
    logger.info(f"代码写手 (Hand):  {coding_provider}")
    logger.info(f"输出目录:         {base_dir}")

    try:

        loader = DataLoader(settings.DATA_PATH_STOCK, settings.DATA_PATH_INDEX)    
        data_bundle = loader.load() 
          
    except Exception as e:
        logger.critical(f"数据加载失败: {e}")
        return

    try:
        # 实例化构思者
        llm_ideation = get_llm_instance(ideation_provider)
        # 实例化执行者
        llm_coding = get_llm_instance(coding_provider)
    except ValueError as e:
        logger.critical(str(e))
        return
        
    executor = Executor(data_bundle)

    # 4. 获取任务
    tasks = settings.FACTOR_MINING_TASKS
    if not tasks:
        logger.warning("任务列表为空。")
        return

    logger.info(f"即将开始执行 {len(tasks)} 个挖掘任务...")

    for i, task in enumerate(tasks):
        base_idea = task.get('idea')
        num = task.get('num_variations', settings.DEFAULT_NUM_VARIATIONS)
        
        if not base_idea: continue

        logger.info(f"\n====== [任务 {i+1}/{len(tasks)}] 种子: {base_idea} ======")
        
        # === 阶段 1: 构思 (使用 llm_ideation) ===
        # 注意：这里调用的是“构思模型”
        ideas = llm_ideation.ideation(base_idea, num)
        
        if not ideas:
            logger.error("构思阶段未返回有效结果。")
            continue
            
        logger.info(f"构思完成: 生成 {len(ideas)} 个因子变体。")

        # === 阶段 2: 编码与执行 (使用 llm_coding) ===
        for j, idea in enumerate(ideas):
            logger.info(f"\n>>> 正在处理变体 {j+1}/{len(ideas)} ...")
            
            # 注意：这里传入的是“代码模型”
            process_single_factor_idea(
                llm_coding=llm_coding,     
                executor=executor,
                idea_dict=idea,
                code_output_dir=code_dir,
                factor_output_dir=factor_dir,
                recorder=recorder,
                seed_idea=base_idea,
                provider_name=ideation_provider 
            )
            
            # 稍作休整，防止 API 限流
            time.sleep(1)

    logger.info("\n====== 所有任务执行完毕 ======")
    logger.info(f"因子汇总表已保存至: {recorder.filepath}")

if __name__ == "__main__":
    main()