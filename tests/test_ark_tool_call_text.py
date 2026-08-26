"""方舟 GLM 文本格式工具调用识别（parse-ark-text-tool-call delta）。

线上事故（601700 复盘）：超时后 Agent 以 <tool_call>NAME<arg_key>K</arg_key>
<arg_value>V</arg_value></tool_call> 文本格式发起重试，harness 不识别 →
整段 XML 作为最终回答流给用户、重试从未执行（incidents 018/020 家族）。
"""

from __future__ import annotations

from finance_agent.harness.ark_tool_call_text import ArkToolCallTextFilter


def _feed_split(filt: ArkToolCallTextFilter, text: str, chunk: int = 3) -> str:
    """按固定 chunk 长度切分喂入，拼接下发结果。"""
    out = []
    for i in range(0, len(text), chunk):
        out.append(filt.feed(text[i : i + chunk]))
    return "".join(out)


class TestArkToolCallTextFilter:
    def test_complete_block_converted_to_call(self):
        """完整文本块转为结构化调用，块文本不进正文。"""
        f = ArkToolCallTextFilter()
        emitted = _feed_split(
            f,
            "重试一次。<tool_call>run_deep_analysis"
            "<arg_key>stock_code</arg_key><arg_value>601700</arg_value>"
            "<arg_key>stock_name</arg_key><arg_value>风范股份</arg_value>"
            "</tool_call>",
        )
        assert emitted == "重试一次。"
        f.finish()
        assert f.calls == [
            {
                "name": "run_deep_analysis",
                "arguments": {"stock_code": "601700", "stock_name": "风范股份"},
            }
        ]

    def test_tag_split_across_chunks_detected(self):
        """标签跨增量分割（逐字符喂入的极端情形）仍可识别。"""
        f = ArkToolCallTextFilter()
        text = (
            "A<tool_call>web_search<arg_key>query</arg_key>"
            "<arg_value>今日热门</arg_value></tool_call>"
        )
        emitted = _feed_split(f, text, chunk=1)
        assert emitted == "A"
        f.finish()
        assert f.calls == [{"name": "web_search", "arguments": {"query": "今日热门"}}]

    def test_plain_text_passthrough_with_bounded_holdback(self):
        """无标签正文透传：单次 feed 立即下发，至多保留前缀长度的待定尾部。"""
        f = ArkToolCallTextFilter()
        emitted = f.feed(
            "普通回答，没有任何标签。" + "tool"[:4]
        )  # 尾部是 <tool_call> 的部分前缀吗？——不是，先看纯文本
        # "tool" 不是 "<tool_call" 前缀（缺 <），应全部立即下发
        assert emitted.endswith("tool")
        tail = f.finish()
        assert emitted + tail == "普通回答，没有任何标签。tool"

    def test_prefix_like_tail_held_back_then_flushed(self):
        """尾部恰为标签前缀时保持住，流结束补发。"""
        f = ArkToolCallTextFilter()
        emitted = f.feed("结论<tool_ca")
        assert emitted == "结论", f"疑似前缀不得提前下发: {emitted!r}"
        tail = f.finish()
        assert tail == "<tool_ca"

    def test_unclosed_block_returned_verbatim_at_finish(self):
        """未闭合块流结束时原样返回，不吞内容。"""
        f = ArkToolCallTextFilter()
        emitted = f.feed("前文。<tool_call>run_deep_analysis<arg_key>x")
        assert emitted == "前文。"
        tail = f.finish()
        assert tail == "<tool_call>run_deep_analysis<arg_key>x"
        assert f.calls == []

    def test_multiple_blocks_and_text_between(self):
        """多个块 + 块间正常文本：全部调用解析，块间文本下发。"""
        f = ArkToolCallTextFilter()
        emitted = _feed_split(
            f,
            "<tool_call>a<arg_key>k</arg_key><arg_value>1</arg_value></tool_call>"
            "之间文本"
            "<tool_call>b<arg_key>k</arg_key><arg_value>2</arg_value></tool_call>",
        )
        assert emitted == "之间文本"
        f.finish()
        assert [c["name"] for c in f.calls] == ["a", "b"]

    def test_malformed_block_dropped_with_no_call(self):
        """块闭合但内容无法解析（缺名称）：不炸、不产出调用，块文本不下发。"""
        f = ArkToolCallTextFilter()
        f.feed("<tool_call>???</tool_call>尾巴")
        f.finish()
        assert f.calls == []
