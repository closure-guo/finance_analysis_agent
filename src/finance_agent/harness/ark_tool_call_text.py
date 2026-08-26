"""方舟 GLM 文本格式工具调用识别（parse-ark-text-tool-call delta）。

方舟 GLM 在部分轮次把工具调用以原生文本格式输出在 content 里：
``<tool_call>NAME<arg_key>K</arg_key><arg_value>V</arg_value>…</tool_call>``
而非 OpenAI 结构化 tool_calls 字段。harness 不识别时整段 XML 作为最终
回答流给用户、意图中的工具调用不会执行（601700 复盘；incidents 018
方舟兼容家族）。

ArkToolCallTextFilter 以流式状态机工作：
- 正常正文照常下发，仅为检测开标签而持有至多 len(tag)-1 个待定尾部字符
  （下发延迟有界，不为检测整段缓冲）；
- 命中开标签后进入块累积，闭标签到达即解析为结构化调用（文本不下发）；
- 流结束时未闭合的疑似块原样作为正文返回（不吞内容）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_TAG_OPEN = "<tool_call>"
_TAG_CLOSE = "</tool_call>"
_ARG_PATTERN = re.compile(r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", re.DOTALL)
_NAME_PATTERN = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*", re.DOTALL)


def _split_keep_prefix(buf: str) -> tuple[str, str]:
    """把缓冲切为（可安全下发的文本, 疑似开标签前缀的尾部）。

    尾部最长 len(_TAG_OPEN)-1：正文下发延迟有界。
    """
    for k in range(min(len(_TAG_OPEN) - 1, len(buf)), 0, -1):
        if buf.endswith(_TAG_OPEN[:k]):
            return buf[:-k], buf[-k:]
    return buf, ""


class ArkToolCallTextFilter:
    """流式文本过滤器：识别文本格式工具调用并转为结构化调用。

    用法：
        f = ArkToolCallTextFilter()
        for delta in stream:
            emit(f.feed(delta))          # 返回值作为正文下发
        emit(f.finish())                 # 流结束补发残留文本
        calls = f.calls                  # [{"name": str, "arguments": dict[str, str]}]
    """

    def __init__(self) -> None:
        self._pending = ""
        self._in_tool = False
        # 元素结构：name=str、arguments=dict[str, str]
        self.calls: list[dict[str, Any]] = []

    def feed(self, text: str) -> str:
        """喂入流式增量，返回应立即作为正文下发的文本。"""
        self._pending += text
        out: list[str] = []
        while self._pending:
            if not self._in_tool:
                if _TAG_OPEN in self._pending:
                    before, _, self._pending = self._pending.partition(_TAG_OPEN)
                    if before:
                        out.append(before)
                    self._in_tool = True
                else:
                    emit, keep = _split_keep_prefix(self._pending)
                    if emit:
                        out.append(emit)
                    self._pending = keep
                    break  # 剩余为疑似前缀，等待更多增量
            # 工具块内：只认闭标签，块内容一律不进正文
            if _TAG_CLOSE in self._pending:
                block, _, self._pending = self._pending.partition(_TAG_CLOSE)
                self._parse_block(block)
                self._in_tool = False  # 块结束回正常模式；多块由下一轮识别
                continue
            break  # 块未闭合，等待更多增量
        return "".join(out)

    def finish(self) -> str:
        """流结束：返回残留文本。未闭合的疑似块原样吐回（不吞内容）。"""
        rest, self._pending = self._pending, ""
        if self._in_tool:
            self._in_tool = False
            return _TAG_OPEN + rest
        return rest

    def _parse_block(self, block: str) -> None:
        """解析一个已闭合的块内容为结构化调用；无法解析时回退为正文并告警。"""
        name_match = _NAME_PATTERN.match(block)
        if not name_match:
            logger.warning("方舟文本工具调用块无法解析（缺名称），原样回退正文: %r", block[:120])
            return
        name = name_match.group(1)
        args: dict[str, str] = dict(_ARG_PATTERN.findall(block))
        self.calls.append({"name": name, "arguments": args})
