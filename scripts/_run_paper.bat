@echo off
chcp 65001 >nul
cd /d "C:\Users\Administrator\ DSH ??????\deepseek-harness-quant"
set PYTHONUTF8=1
set NO_PROXY=*
"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" scripts\paper_trade.py >> logs\paper_auto.log 2>&1
