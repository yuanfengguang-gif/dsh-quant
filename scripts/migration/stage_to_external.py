# -*- coding: utf-8 -*-
"""scripts/migration/stage_to_external.py —— 把待迁移文件按类别整理到目标文件夹

用途：生成一个「自带说明」的搬运目录，每类文件对应新电脑的哪个目标路径一目了然。

目录结构：
    <DEST>/
      01_核心数据库_必搬/        → 新机 ...\\deepseek-harness-quant\\data\\cache\\
      02_源数据库_建议搬/        → 同上（体积大，可按需）
      03_项目外依赖/
          .dsh_skills_tdx-aidata/ → 新机 C:\\Users\\<用户>\\.dsh\\skills\\tdx-aidata\\
          dsh-desktop.env       → 新机 C:\\Users\\<用户>\\dsh-desktop\\.env（含密钥，用完删除）
      04_计划任务XML/            → schtasks /create /xml 导入
      05_迁移脚本与清单/         → 参考（验收脚本/依赖清单/数据清单）
      README_如何还原.md         → 逐步说明
      manifest.sha256.txt        → 校验清单

用法：
    python scripts/migration/stage_to_external.py --dest "D:\\DSH量化项目数据"
    python scripts/migration/stage_to_external.py --dest "..." --dry-run
    python scripts/migration/stage_to_external.py --dest "..." --hash   # 额外算 SHA256（慢）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent.parent
CACHE = BASE / "data" / "cache"
HOME = Path.home()

ESSENTIAL = ["bars.db", "valuation.db", "hist_mv.db", "finance.db", "finance_quality.db",
             "tdx_finance.db", "tdx_capital.db", "stock_basic.db", "tdx_snapshot.db",
             "name_history.db", "rzrq.db", "lhb.db", "limitup.db", "consensus.db",
             "st_history.db", "industry.db", "bars_incr.db"]

SOURCE = ["tdx_base.db", "bars_tdx.db", "finance_csmar.db"]

EXTERNAL = {
    "skills": (HOME / ".dsh" / "skills" / "tdx-aidata", ".dsh_skills_tdx-aidata"),
    "env": (HOME / "dsh-desktop" / ".env", "dsh-desktop.env"),
}

README = """# DSH 量化项目 · 迁移搬运包

> 生成时间：{ts}
> 源机器：{src}
> 本包用途：把「新电脑跑不起来」的东西补上（代码已通过 GitHub 同步，无需在此包内）

---

## 一、请先在新电脑上做这一步（代码）

```powershell
git clone https://github.com/yuanfengguang-gif/dsh-quant.git "C:\\Users\\<你的用户名>\\ DSH 量化交易系统\\deepseek-harness-quant"
```

> ⚠️ **路径请保持完全一致**（`Administrator\\` 后面有一个空格）。
> 项目里有 159 个文件、213 处硬编码 `C:\\Users\\Administrator`；路径一致才能零改动运行。

---

## 二、本包各类文件的【目标位置】

| 本包目录 | 拷到新电脑的哪里 | 说明 |
|---|---|---|
| `01_核心数据库_必搬\\` | `<项目>\\data\\cache\\` | **17 个库 / {gb1} GB**，缺任何一个都跑不起来 |
| `02_源数据库_建议搬\\` | `<项目>\\data\\cache\\` | **3 个库 / {gb2} GB**（通达信原始导出 + CSMAR）；不拷也能跑，但以后重建数据要重新下载 |
| `03_项目外依赖\\.dsh_skills_tdx-aidata\\` | `C:\\Users\\<用户名>\\.dsh\\skills\\tdx-aidata\\`（整目录） | 通达信 API 技能，含 8 个 DLL，**必须整目录拷** |
| `03_项目外依赖\\dsh-desktop.env` | `C:\\Users\\<用户名>\\dsh-desktop\\.env` | ⚠️ **含 API 密钥**；拷完请从移动硬盘删除 |
| `04_计划任务XML\\` | 用 `schtasks /create /xml` 导入 | 7 个每日自动任务 |
| `05_迁移脚本与清单\\` | 参考，不用拷 | 验收脚本 / 依赖清单 / 数据清单 |

---

## 三、还原步骤（按顺序）

```powershell
# 1) 装 Python 3.13（勾选 Add to PATH），然后装依赖
cd "<项目>"
pip install -r scripts\\migration\\requirements_frozen.txt

# 2) 拷数据库（把 E: 换成你的移动硬盘盘符）
robocopy "E:\\DSH量化项目数据\\01_核心数据库_必搬" "<项目>\\data\\cache" /J /R:1 /W:1
robocopy "E:\\DSH量化项目数据\\02_源数据库_建议搬" "<项目>\\data\\cache" /J /R:1 /W:1

# 3) 拷项目外依赖
robocopy "E:\\DSH量化项目数据\\03_项目外依赖\\.dsh_skills_tdx-aidata" "C:\\Users\\<用户名>\\.dsh\\skills\\tdx-aidata" /E
copy  "E:\\DSH量化项目数据\\03_项目外依赖\\dsh-desktop.env" "C:\\Users\\<用户名>\\dsh-desktop\\.env"

# 4) 导入计划任务（管理员 PowerShell）
Get-ChildItem "E:\\DSH量化项目数据\\04_计划任务XML\\*.xml" | ForEach-Object {{
    schtasks /create /xml $_.FullName /tn $_.BaseName /f
}}

# 5) 验收（关键！全部 OK 才算迁移成功）
python scripts\\migration\\verify_after_migration.py
```

---

## 四、新电脑必须先装的软件

| 软件 | 为什么 | 验证方式 |
|---|---|---|
| **Python 3.13** | 全局环境（原机无 venv） | `python -V` |
| **通达信金融终端** | `tdx-aidata` 带 mfc100/msvcp100 等 DLL，是**本地客户端 API**；不装就取不到新数据 | 能登录行情即可 |
| Git（可选） | 拉代码用 | `git --version` |

---

## 五、本包【不包含】的东西（不用找）

| 内容 | 体积 | 为什么不在包里 |
|---|---|---|
| 代码 / 脚本 / 文档 / 配置模板 | — | **已通过 GitHub 同步**（`yuanfengguang-gif/dsh-quant`） |
| 归档旧库（`bars_before_qfq_switch_*.db` 等） | 11.37 GB | 只是回滚保险，新机不需要 |
| `data\\tdx_factor\\`（通达信因子批量下载） | 496 MB | 可重新下载 |
| `logs\\` / `__pycache__` | — | 运行产物 |

---

## 六、长期一致性建议

```
A 机（现这台）= 数据主库：唯一跑每日更新
B 机（新电脑）= 计算节点：只读数据，跑因子/回测
        ↓ 每周 robocopy /MIR 单向同步 A → B
```

两台都写数据 = 必然分叉。`/MIR` 是逐字节镜像，比 Git 更适合大二进制。
"""


def human(n: float) -> str:
    return f"{n/1024/1024/1024:.2f} GB" if n > 1024**3 else f"{n/1024/1024:.1f} MB"


def copy_group(files, dest: Path, label: str, dry: bool) -> tuple[int, int]:
    dest.mkdir(parents=True, exist_ok=True)
    n = total = 0
    for f in files:
        src = CACHE / f
        if not src.exists():
            print(f"    [SKIP] {f} 不存在")
            continue
        size = src.stat().st_size
        print(f"    [COPY] {f:44s} {human(size)}", flush=True)
        if not dry:
            shutil.copy2(src, dest / f)
        n += 1
        total += size
    print(f"  -> {label}: {n} 个文件, {human(total)}")
    return n, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True, help="目标文件夹，例如 D:\\DSH量化项目数据")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hash", action="store_true", help="额外计算 SHA256（大库很慢）")
    args = ap.parse_args()

    dest = Path(args.dest)
    print(f"目标: {dest}")
    print(f"源  : {BASE}\n")

    d1 = dest / "01_核心数据库_必搬"
    d2 = dest / "02_源数据库_建议搬"
    d3 = dest / "03_项目外依赖"
    d4 = dest / "04_计划任务XML"
    d5 = dest / "05_迁移脚本与清单"

    need = sum((CACHE / f).stat().st_size for f in ESSENTIAL + SOURCE if (CACHE / f).exists())
    print(f"需要空间约 {human(need)}")
    if dest.exists():
        free = shutil.disk_usage(dest).free
        print(f"目标剩余 {human(free)}")
        if free < need * 1.05:
            print("  [ERROR] 空间不足，请换盘或先清理")
            return 1
    elif not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] 核心数据库")
    n1, s1 = copy_group(ESSENTIAL, d1, "核心数据库", args.dry_run)
    print("\n[2/4] 源数据库")
    n2, s2 = copy_group(SOURCE, d2, "源数据库", args.dry_run)

    print("\n[3/4] 项目外依赖")
    d3.mkdir(parents=True, exist_ok=True)
    for key, (src, name) in EXTERNAL.items():
        if not src.exists():
            print(f"    [SKIP] {src} 不存在")
            continue
        tgt = d3 / name
        if src.is_dir():
            print(f"    [COPY] {name}/  ({sum(f.stat().st_size for f in src.rglob('*') if f.is_file())/1024/1024:.1f} MB)", flush=True)
            if not args.dry_run:
                if tgt.exists():
                    shutil.rmtree(tgt)
                shutil.copytree(src, tgt)
        else:
            print(f"    [COPY] {name}  ({src.stat().st_size} bytes)", flush=True)
            if not args.dry_run:
                shutil.copy2(src, tgt)

    print("\n[4/4] 计划任务 + 迁移脚本")
    d4.mkdir(parents=True, exist_ok=True)
    tasks = BASE / "output" / "migration" / "tasks"
    tn = 0
    if tasks.is_dir():
        for f in tasks.glob("*.xml"):
            print(f"    [COPY] tasks/{f.name}", flush=True)
            if not args.dry_run:
                shutil.copy2(f, d4 / f.name)
            tn += 1
    d5.mkdir(parents=True, exist_ok=True)
    for f in (BASE / "scripts" / "migration").glob("*"):
        if f.is_file():
            if not args.dry_run:
                shutil.copy2(f, d5 / f.name)
    print(f"  -> 计划任务 {tn} 个 + 迁移脚本已复制")

    if not args.dry_run:
        gb1 = sum((CACHE / f).stat().st_size for f in ESSENTIAL if (CACHE / f).exists()) / 1024**3
        gb2 = sum((CACHE / f).stat().st_size for f in SOURCE if (CACHE / f).exists()) / 1024**3
        (dest / "README_如何还原.md").write_text(
            README.format(ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
                          src=BASE, gb1=f"{gb1:.2f}", gb2=f"{gb2:.2f}"),
            encoding="utf-8")

        # manifest
        lines = ["# 迁移包文件清单（新机可用 certutil -hashfile 逐项核对）",
                 f"# 生成 {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
        for root in (d1, d2, d3, d4, d5):
            if not root.exists():
                continue
            for f in sorted(root.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(dest).as_posix()
                if args.hash:
                    h = hashlib.sha256()
                    with open(f, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 22), b""):
                            h.update(chunk)
                    lines.append(f"{h.hexdigest()}  {f.stat().st_size:>12d}  {rel}")
                else:
                    lines.append(f"{'':64s}  {f.stat().st_size:>12d}  {rel}")
                print(f"  清单: {rel}", flush=True)
        (dest / "manifest.sha256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n完成。目录：")
    for p in sorted(dest.iterdir()):
        if p.is_dir():
            sz = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            print(f"  {p.name:28s} {human(sz)}  ({sum(1 for f in p.rglob('*') if f.is_file())} 文件)")
        else:
            print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
