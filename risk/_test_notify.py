# -*- coding: utf-8 -*-
"""临时：测试 Server酱 通知是否打通。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from risk.alert_engine import AlertEngine, Alert

eng = AlertEngine()
# 发一条测试预警
r = eng.notify([Alert("drawdown", "info", "这是一条 DSHQuant 预警测试：通知通道已打通")])
print("发送结果:", r)
