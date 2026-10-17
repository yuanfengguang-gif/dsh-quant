# -*- coding: utf-8 -*-
"""QF-LLM 沙箱：subprocess 隔离执行 AI 生成的因子代码。

安全边界（对应视频口径"禁止 IO + 白名单库 + 超时杀进程 + 输出格式检查"）：
1. 静态 AST 检查：只允许 import numpy/pandas；禁止 IO / 危险内建 / 危险属性调用。
2. subprocess 隔离：超时直接 kill。
3. 受限 builtins + 受限 import hook。
4. 输出格式检查：必须产出对齐 panel 索引的 pd.Series。
"""
from __future__ import annotations

import ast
import builtins
import os
import subprocess
import sys
import tempfile
import textwrap

import numpy as np
import pandas as pd

# 只允许这两个库（本 skill 评分/因子计算仅需 numpy/pandas）
ALLOWED_IMPORT_ROOTS = {"numpy", "pandas"}

# 受限 builtins 白名单
ALLOWED_BUILTIN_NAMES = {
    "abs", "min", "max", "sum", "len", "range", "enumerate", "zip", "sorted",
    "reversed", "round", "pow", "divmod", "float", "int", "bool", "str", "list",
    "dict", "set", "tuple", "any", "all", "map", "filter", "isinstance", "print",
    "True", "False", "None",
}

# 明确禁止的名字 / 属性（IO 与逃逸）
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "globals", "locals", "getattr", "setattr",
    "delattr", "input", "exit", "quit", "vars", "dir", "help",
}
FORBIDDEN_ATTRS = {
    # pandas / numpy 的 IO 与序列化出口
    "read_csv", "to_csv", "read_parquet", "to_parquet", "read_pickle", "to_pickle",
    "read_excel", "to_excel", "read_json", "to_json", "read_sql", "to_sql",
    "read_html", "to_html", "read_clipboard", "to_clipboard", "read_hdf", "to_hdf",
    "load", "save", "savez", "savetxt", "loadtxt", "fromfile", "tofile",
    "genfromtxt", "npzfile", "read_feather", "to_feather", "read_stata", "to_stata",
}


def inspect_code(code: str) -> None:
    """静态 AST 检查，违规直接抛 PermissionError。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SyntaxError(f"因子代码语法错误: {e}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    raise PermissionError(f"禁止 import: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                raise PermissionError(f"禁止 from-import: {node.module}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                raise PermissionError(f"禁止使用: {node.id}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in FORBIDDEN_NAMES:
                raise PermissionError(f"禁止调用: {f.id}")
            if isinstance(f, ast.Attribute) and f.attr in FORBIDDEN_ATTRS:
                raise PermissionError(f"禁止调用 IO/序列化: {f.attr}")


# 子进程 runner 源码：读取 panel + 因子代码 → 受限 exec → 调 factor(panel) → 输出 Series
_RUNNER = textwrap.dedent('''
    import builtins, pickle, sys
    import numpy as np, pandas as pd

    def _safe_import(name, *a, **k):
        if name.split(".")[0] not in ("numpy", "pandas"):
            raise ImportError("禁止导入: " + name)
        return __import__(name, *a, **k)

    safe_builtins = {n: getattr(builtins, n) for n in %r if hasattr(builtins, n)}
    safe_builtins["__import__"] = _safe_import

    panel = pickle.load(open(sys.argv[1], "rb"))
    code = open(sys.argv[2], encoding="utf-8").read()
    g = {"np": np, "pd": pd, "numpy": np, "pandas": pd, "__builtins__": safe_builtins}
    exec(compile(code, "factor.py", "exec"), g, g)

    fn = g.get("factor")
    if not callable(fn):
        raise RuntimeError("必须定义 factor(panel) 函数")

    out = fn(panel)
    if not isinstance(out, pd.Series):
        raise RuntimeError("factor(panel) 必须返回 pd.Series，实际为: " + type(out).__name__)
    out = out.reindex(panel.index)
    pickle.dump(out, open(sys.argv[3], "wb"))
''') % sorted(ALLOWED_BUILTIN_NAMES)


def run(code: str, panel: pd.DataFrame = None, panel_path: str = None,
        timeout: float = 30.0) -> pd.Series:
    """在沙箱中执行因子代码，返回对齐 panel.index 的得分 Series。

    panel 或 panel_path 二选一；panel_path 用于复用已序列化的大面板（避免每候选重复 pickle）。
    """
    inspect_code(code)
    with tempfile.TemporaryDirectory() as d:
        if panel_path is not None:
            panel_p = panel_path
        else:
            if panel is None:
                raise ValueError("需提供 panel 或 panel_path")
            panel_p = os.path.join(d, "panel.pkl")
            panel.to_pickle(panel_p)
        code_p = os.path.join(d, "factor.py")
        out_p = os.path.join(d, "out.pkl")
        runner_p = os.path.join(d, "runner.py")

        with open(code_p, "w", encoding="utf-8") as f:
            f.write(code)
        with open(runner_p, "w", encoding="utf-8") as f:
            f.write(_RUNNER)

        try:
            proc = subprocess.run(
                [sys.executable, runner_p, panel_p, code_p, out_p],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"沙箱超时（>{timeout}s），已杀进程")

        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "").strip()[-600:]
            raise RuntimeError(f"沙箱执行失败: {msg}")

        return pd.read_pickle(out_p)
