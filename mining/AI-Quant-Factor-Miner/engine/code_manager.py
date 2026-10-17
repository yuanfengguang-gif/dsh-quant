# engine/code_manager.py
import os
import re
import sys
import importlib.util
from utils.logger import logger

class CodeManager:
    @staticmethod
    def _get_unique_factor_name(base_name, output_dir):
        """
        生成唯一的文件名，防止覆盖已有文件
        例如: 如果 AlphaTest.py 存在，则返回 AlphaTest_v1
        """
        counter = 0
        candidate_name = base_name
        
        while True:
            file_path = os.path.join(output_dir, f"{candidate_name}.py")
            if not os.path.exists(file_path):
                return candidate_name
            
            counter += 1
            candidate_name = f"{base_name}_v{counter}"

    @staticmethod
    def save_and_load_function(code_string, factor_name, output_dir, specific_name=None):
        """
        清洗代码，保存文件，并动态加载模块
        
        Args:
            code_string: AI 生成的代码字符串
            factor_name: 原始函数名 (def Alpha...)，用于 getattr 获取函数对象
            output_dir: 保存目录
            specific_name: 指定文件名 (不含.py)。
                           - 如果为 None，则自动生成唯一名 (如 Alpha_v1)。
                           - 如果有值，则强制覆盖该文件 (用于修复模式)。
                           
        Returns:
            (func_object, unique_name, file_path)
        """
        try:
            code_string = re.sub(r"^```python\n", "", code_string, flags=re.MULTILINE)
            code_string = re.sub(r"\n```$", "", code_string, flags=re.MULTILINE)
            code_string = code_string.strip()

            if not code_string:
                logger.error("AI 返回了空代码。")
                return None, factor_name, ""

            os.makedirs(output_dir, exist_ok=True)

            if specific_name:
                unique_name = specific_name 
            else:
                unique_name = CodeManager._get_unique_factor_name(factor_name, output_dir) 

            filepath = os.path.join(output_dir, f"{unique_name}.py")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code_string)
            
            logger.info(f"代码已保存至: {filepath}")

            module_name = unique_name
            
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                logger.error(f"无法创建模块 spec: {filepath}")
                return None, unique_name, filepath
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, factor_name):
                return getattr(module, factor_name), unique_name, filepath
            
            import inspect
            for name, obj in inspect.getmembers(module, inspect.isfunction):
                if obj.__module__ == module_name:
                    logger.warning(f"未找到 {factor_name}，自动匹配到函数: {name}")
                    return obj, unique_name, filepath
            
            logger.error(f"模块中未找到有效函数: {factor_name}")
            return None, unique_name, filepath

        except Exception as e:
            logger.error(f"代码保存/加载出错: {e}")
            return None, factor_name, ""