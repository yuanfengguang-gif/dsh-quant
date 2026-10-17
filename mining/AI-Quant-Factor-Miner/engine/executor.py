# engine/executor.py
import os
import pandas as pd
import traceback  
from config import settings
from utils.logger import logger

class Executor:
    def __init__(self, data_bundle):
        self.data_bundle = data_bundle

    def run(self, factor_func, factor_name, output_dir):
        """
        执行因子计算逻辑
        Returns:
            tuple: (bool is_success, str message)
            - 成功: (True, "Success")
            - 失败: (False, "错误详情或堆栈信息")
        """
        try:
            logger.info(f"正在执行函数: {factor_name} ...")
            
            df_raw_input = self.data_bundle['stock'].copy()
            df_index_input = self.data_bundle['index'].copy() if self.data_bundle['index'] is not None else None
            
            df_result = factor_func(
                df_raw=df_raw_input,
                df_index=df_index_input
            )


            if not isinstance(df_result, pd.DataFrame):
                msg = f"Return type error: Expected pd.DataFrame, got {type(df_result)}"
                logger.error(msg)
                return False, msg  

            expected_base_cols = settings.REQUIRED_OUTPUT_COLS
            missing_cols = [col for col in expected_base_cols if col not in df_result.columns]
            if missing_cols:
                msg = f"Missing required columns: {missing_cols}. Ensure you reset_index."
                logger.error(msg)
                return False, msg  

            if factor_name not in df_result.columns:
                msg = f"Result missing factor column: '{factor_name}'. Check your column renaming logic."
                logger.error(msg)
                return False, msg 

            final_cols = expected_base_cols + [factor_name]
            
            df_final = df_result[final_cols].copy()
            
            if 'SecuCode' in df_final.columns:
                df_final['SecuCode'] = df_final['SecuCode'].astype(str).str.zfill(6).str.slice(0, 6)

            output_filepath = os.path.join(output_dir, f"{factor_name}.parquet")
            df_final.to_parquet(output_filepath, index=False)
            
            logger.info(f"保存成功: {output_filepath}")
            return True, "Success"

        except Exception as e:
            
            error_msg = str(e)
            full_traceback = traceback.format_exc()
            
            logger.error(f"执行时发生运行时错误: {error_msg}")
            
            return False, full_traceback