"""block bootstrap 显著性 + 夏普异常拦截（spec「统计显著性与不确定性报告」）。"""

from __future__ import annotations

from collections.abc import Sequence

from evals.stats import block_bootstrap_stat, sharpe

SANITY_SHARPE_LIMIT = 3.0


def validate_sanity(sharpe_value: float, sanity_note: str | None) -> str:
    """Sharpe > 3 的批次必须附 sanity check 说明（样本期/回撤/换手），否则无效。

    空白说明视同缺失。
    """
    if sharpe_value > SANITY_SHARPE_LIMIT and not (sanity_note and sanity_note.strip()):
        return "invalid"
    return "valid"


def block_length_sensitivity(
    returns: Sequence[float],
    *,
    blocks: tuple[int, ...] = (10, 20, 40),
    B: int = 1_000,  # noqa: N803 — 接口冻结：参数名 B 与 evals.stats 契约一致
    seed: int = 42,
) -> dict[str, tuple[float, float]]:
    """块长敏感性：多块长下 Sharpe CI 并排披露（契约要求附说明）。"""
    return {
        str(b): block_bootstrap_stat(returns, sharpe, block_size=b, B=B, seed=seed) for b in blocks
    }
