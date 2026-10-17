# data_loader/loader.py
import pandas as pd
import os
from utils.logger import logger

class DataLoader:
    def __init__(self, stock_path, index_path):
        self.stock_path = stock_path
        self.index_path = index_path
        self.data_bundle = None

    def load(self):
        """加载数据并返回字典包"""
        if self.data_bundle is not None:
            return self.data_bundle

        logger.info("正在加载原始数据 (全局一次)...")
        
        if not os.path.exists(self.stock_path) or not os.path.exists(self.index_path):
            logger.error(f"数据文件不存在。请检查路径:\n{self.stock_path}\n{self.index_path}")
            raise FileNotFoundError("数据文件未找到")

        try:
            df_stock = pd.read_parquet(self.stock_path)
            df_index = pd.read_parquet(self.index_path)
            
            self.data_bundle = {
                "stock": df_stock,
                "index": df_index
            }
            logger.info("所有原始数据加载完毕。")
            return self.data_bundle
        except Exception as e:
            logger.error(f"加载数据时出错: {e}")
            raise e