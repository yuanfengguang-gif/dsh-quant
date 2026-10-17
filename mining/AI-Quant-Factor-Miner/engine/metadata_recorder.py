# engine/metadata_recorder.py
import csv
import os
import pandas as pd
from datetime import datetime
from utils.logger import logger
from datetime import datetime

class MetadataRecorder:
    def __init__(self, filepath=None):
        """
        初始化记录器
        :param filepath: CSV 文件的保存路径。如果为 None，则使用默认路径。
        """
        if filepath:
            self.filepath = filepath
        else:
            # 默认回退路径（防止 main.py 没传参时报错）
            self.filepath = "output/factor_records.csv"
            
        # 自动创建父目录
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        
        # 初始化 CSV 文件头（如果文件不存在）
        self._init_csv()

    def _init_csv(self):
        """如果不文件存在，写入表头"""
        if not os.path.exists(self.filepath):
            try:
                columns = [
                    "Timestamp", 
                    "Provider", 
                    "Seed_Idea", 
                    "Factor_Name", 
                    "Status", 
                    "Code_Path", 
                    "Formula", 
                    "Description"
                ]
                df = pd.DataFrame(columns=columns)
                df.to_csv(self.filepath, index=False, encoding="utf-8-sig")
            except Exception as e:
                logger.error(f"初始化 CSV 记录表失败: {e}")

    def add_record(self, provider, seed_idea, factor_name, formula, description, status, code_path):
        """
        追加一条记录
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            new_row = {
                "Timestamp": timestamp,
                "Provider": provider,
                "Seed_Idea": seed_idea,
                "Factor_Name": factor_name,
                "Status": status,
                "Code_Path": code_path,
                "Formula": formula,
                "Description": description
            }
            
            # 使用 pandas 追加模式 (mode='a')
            df = pd.DataFrame([new_row])
            df.to_csv(self.filepath, mode='a', header=False, index=False, encoding="utf-8-sig")
            logger.info(f"已记录因子状态: {status}")
            
        except Exception as e:
            logger.error(f"写入 CSV 记录失败: {e}")