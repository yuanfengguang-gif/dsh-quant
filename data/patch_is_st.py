# -*- coding: utf-8 -*-
"""data/patch_is_st.py —— 给通达信 daily_bar 补 is_st 字段

策略（分两段，诚实标注）：
  2020-06 起 → 用 valuation.db 的 isST（PIT 准确，逐日）
  2020-06 前 → 用 stock_info.name 含 "ST"（近似；仅反映当前名称，有前视偏差）
输出：bars_tdx.db 的 daily_bar.is_st 更新；并生成 is_st 覆盖报告
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = Path(r"D:\Programs\DSH Projects\DSH Quant\data\cache")


def main():
    con = sqlite3.connect(str(C / "bars_tdx.db"))
    con.execute("PRAGMA synchronous=OFF")

    print("=== 1) 从 valuation.db 取 isST（2020-06 起）===")
    conv = sqlite3.connect(str(C / "valuation.db"))
    val = pd.read_sql("SELECT date, code, isST FROM valuation", conv)
    conv.close()
    # code: 6位 → xxx.SZ/SH/BJ（按前缀判断）
    def to_code(c):
        c = str(c).zfill(6)
        if c.startswith(("6", "9")):
            return f"{c}.SH"
        if c.startswith(("0", "2", "3")):
            return f"{c}.SZ"
        if c.startswith(("4", "8")):
            return f"{c}.BJ"
        return f"{c}.SZ"
    val["code"] = val["code"].map(to_code)
    val = val.rename(columns={"isST": "is_st_val"})
    print(f"  valuation: {len(val):,} 行, 日期 {val['date'].min()} ~ {val['date'].max()}")

    print("\n=== 2) 从 stock_info 取名称含 ST 的股票（用于 2020 前近似）===")
    info = pd.read_sql("SELECT code, name FROM stock_info", con)
    info["st_name"] = info["name"].astype(str).str.contains("ST", case=False, na=False).astype(int)
    st_codes = set(info[info["st_name"] == 1]["code"])
    print(f"  名称含 ST 的股票: {len(st_codes):,} / {len(info):,}")

    print("\n=== 3) 分区更新 daily_bar.is_st ===")
    total = con.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0]
    print(f"  daily_bar 总量: {total:,}")

    # 3a) 先把 2020-06 起的清空后重新赋值
    con.execute("UPDATE daily_bar SET is_st=0 WHERE date >= '2020-06-01'")
    con.commit()
    val.to_sql("_tmp_isst", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_tmp_isst ON _tmp_isst(code, date)")
    con.execute("""UPDATE daily_bar SET is_st = (
                     SELECT v.is_st_val FROM _tmp_isst v
                     WHERE v.code = daily_bar.code AND v.date = daily_bar.date)
                   WHERE date >= '2020-06-01'
                     AND EXISTS (SELECT 1 FROM _tmp_isst v
                                 WHERE v.code = daily_bar.code AND v.date = daily_bar.date)""")
    con.commit()
    n1 = con.execute("SELECT COUNT(*) FROM daily_bar WHERE date>='2020-06-01' AND is_st=1").fetchone()[0]
    print(f"  2020-06 起 ST 行: {n1:,}")

    # 3b) 2020-06 前用名称近似
    con.execute("UPDATE daily_bar SET is_st=0 WHERE date < '2020-06-01'")
    con.commit()
    if st_codes:
        placeholders = ",".join("?" * len(st_codes))
        con.execute(f"UPDATE daily_bar SET is_st=1 WHERE date < '2020-06-01' AND code IN ({placeholders})",
                    list(st_codes))
        con.commit()
    n2 = con.execute("SELECT COUNT(*) FROM daily_bar WHERE date<'2020-06-01' AND is_st=1").fetchone()[0]
    print(f"  2020-06 前 ST 行（名称近似）: {n2:,}")

    con.execute("DROP TABLE IF EXISTS _tmp_isst")
    con.commit()

    print("\n=== 4) 分年 ST 覆盖 ===")
    for r in con.execute("""SELECT substr(date,1,4) y, COUNT(*) n,
                            SUM(CASE WHEN is_st=1 THEN 1 ELSE 0 END) s
                            FROM daily_bar GROUP BY y ORDER BY y"""):
        print(f"  {r[0]}: {r[1]:>9,} 行, ST {r[2]:>7,} ({r[2]/max(r[1],1)*100:5.2f}%)")
    con.close()
    print("\nis_st 补全完成")


if __name__ == "__main__":
    main()
