"""复现：澄清回复经 text_delta 细粒度流式时，answer 拼接是否丢 \\n。

针对「意图澄清回复实时格式错乱（列表粘连、单 \\n 丢失）、刷新后正常」。
模拟 DeepSeek 真实细粒度流（小 token、\\n 可能独立成 chunk 或在边界），
走 loop.py answer 切片（_safe_think_len + _streamed_answer_len）逻辑，
验证流式 answer 拼接是否等于完整 content。
"""

from __future__ import annotations

from finance_agent.harness.loop import _safe_think_len

# 用户实测错乱场景的文本（列表 + 段间空行）
CONTENT = (
    "根据最新行情与搜索结果，当前 A 股热门集中在通信、半导体存储、机器人与券商板块，相关标的有：\n"
    "1. 中际旭创（300308） —— 光模块龙头，AI 算力订单排至 2027 年\n"
    "2. 寒武纪（688256） —— AI 芯片龙头，创历史新高\n"
    "3. 兆易创新（603986） —— 存储芯片，一字涨停\n"
    "回复序号或股票名称，我将为你运行完整深度分析。"
)


def _simulate_stream(content: str, chunk_size: int) -> str:
    """模拟 loop.py 的 answer 流式：按 chunk_size 切 text_delta，走 _safe_think_len 切片。"""
    streamed = 0
    accumulated = ""
    out = ""
    for i in range(0, len(content), chunk_size):
        accumulated += content[i : i + chunk_size]
        safe_end, dsml = _safe_think_len(accumulated, streamed)
        if safe_end > streamed:
            out += accumulated[streamed:safe_end]
        streamed = safe_end
    # 流末：loop.py 仅在 dsml_calls 非空时补发剩余（408 行）；无 DSML 时无兜底
    return out, streamed


def test_fine_grained_stream_preserves_newlines():
    """多种细粒度切分下，流式 answer 拼接应完整保留 \\n（若有丢失则复现 bug）。"""
    for size in (1, 2, 3, 5, 7, 11):
        out, streamed = _simulate_stream(CONTENT, size)
        assert out == CONTENT, (
            f"chunk_size={size} 流式丢失：拼接长度 {len(out)} != 完整 {len(CONTENT)}；"
            f"缺失尾部：{CONTENT[len(out) :][:50]!r}"
        )
