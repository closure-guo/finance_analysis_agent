"""评估统计核心（spec evaluation「实验对比统计显著性」/ decision-backtest「统计显著性与不确定性报告」）。

- 配对 bootstrap：分数对比按 dataset item 重采样，B=10,000（FinGround 规格）
- block bootstrap：回测时序按交易日块重采样（默认块长 20），保留自相关
- Cohen's κ：标注者一致性
全部函数接受 seed，保证 CI 数值可复现（测试与报告可回归）。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np


def sharpe(returns: Sequence[float]) -> float:
    """年化夏普（rf=0，252 交易日，ddof=1）；std=0 时返回 0.0。"""
    arr = np.asarray(returns, dtype=float)
    if len(arr) < 2:
        return 0.0
    # 恒定序列：直接判等（0.01 等十进制值浮点求和有 ~1e-18 噪声，std 不会精确为 0）
    if np.all(arr == arr[0]):
        return 0.0
    std = float(arr.std(ddof=1))
    if std == 0.0:
        return 0.0
    return float(arr.mean() / std * math.sqrt(252))


def _percentile_ci(samples: np.ndarray, alpha: float) -> tuple[float, float]:
    lo = float(np.percentile(samples, 100 * alpha / 2))
    hi = float(np.percentile(samples, 100 * (1 - alpha / 2)))
    return lo, hi


def paired_bootstrap_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    B: int = 10_000,  # noqa: N803 — 接口冻结：参数名 B 为后续任务依赖契约
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """逐 item 配对重采样 mean(a)-mean(b) 的 95% 百分位 CI（a/b 等长对齐）。"""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if len(arr_a) != len(arr_b) or len(arr_a) == 0:
        raise ValueError("paired bootstrap 要求 a/b 等长且非空")
    rng = np.random.default_rng(seed)
    n = len(arr_a)
    idx = rng.integers(0, n, size=(B, n))
    diffs = arr_a[idx].mean(axis=1) - arr_b[idx].mean(axis=1)
    return _percentile_ci(diffs, alpha)


def _block_indices(
    n: int, block_size: int, rng: np.random.Generator, n_paths: int
) -> list[np.ndarray]:
    """循环块 bootstrap：随机起点、取 ceil(n/block) 个环形块拼接后截断到 n。"""
    n_blocks = math.ceil(n / block_size)
    starts = rng.integers(0, n, size=(n_paths, n_blocks))
    offsets = np.arange(block_size)
    flat = ((starts[:, :, None] + offsets[None, None, :]) % n).reshape(n_paths, -1)
    return [row[:n] for row in flat]


def block_bootstrap_stat(
    series: Sequence[float],
    stat_fn: Callable[[Sequence[float]], float],
    *,
    block_size: int = 20,
    B: int = 1_000,  # noqa: N803 — 接口冻结：参数名 B 为后续任务依赖契约
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """对时序做循环块 bootstrap，返回 stat_fn 的 95% CI。"""
    arr = np.asarray(series, dtype=float)
    if len(arr) == 0:
        raise ValueError("series 不能为空")
    rng = np.random.default_rng(seed)
    stats = np.array([stat_fn(arr[idx]) for idx in _block_indices(len(arr), block_size, rng, B)])
    return _percentile_ci(stats, alpha)


def paired_block_bootstrap_diff(
    a: Sequence[float],
    b: Sequence[float],
    *,
    block_size: int = 20,
    B: int = 1_000,  # noqa: N803 — 接口冻结：参数名 B 为后续任务依赖契约
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """两条对齐日收益时序的 Sharpe 差 CI：同一组块索引同步重采样（配对）。"""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if len(arr_a) != len(arr_b) or len(arr_a) == 0:
        raise ValueError("paired block bootstrap 要求 a/b 等长且非空")
    rng = np.random.default_rng(seed)
    stats = np.array(
        [
            sharpe(arr_a[idx]) - sharpe(arr_b[idx])
            for idx in _block_indices(len(arr_a), block_size, rng, B)
        ]
    )
    return _percentile_ci(stats, alpha)


def cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    """Cohen's κ（无权重）；完全不一致/边界情形安全返回。"""
    if len(labels_a) != len(labels_b):
        raise ValueError("标注序列等长")
    n = len(labels_a)
    if n == 0:
        return 0.0
    categories = sorted(set(labels_a) | set(labels_b))
    idx = {c: i for i, c in enumerate(categories)}
    matrix = np.zeros((len(categories), len(categories)), dtype=int)
    for la, lb in zip(labels_a, labels_b, strict=True):
        matrix[idx[la], idx[lb]] += 1
    po = float(np.trace(matrix)) / n
    pe = float(sum(matrix[i].sum() * matrix[:, i].sum() for i in range(len(categories)))) / (n * n)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)
