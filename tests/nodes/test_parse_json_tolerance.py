# tests/nodes/test_parse_json_tolerance.py
"""parse_json_response 容错测试（incident 016 遗留的行失败问题）。

方舟 GLM-5.2 概率性输出尾逗号 JSON（实测跑批 row 0 炸点：
"Illegal trailing comma before end of array: line 8 column 52"）。
下游节点（debate/trader/risk/fund_manager）解析无 try/except，
parse 层必须自行消化常见格式瑕疵，否则单次坏输出炸整行管线。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from finance_agent.nodes._llm_utils import parse_json_response


class TestTrailingCommaTolerance:
    def test_array_trailing_comma(self):
        """数组末元素后尾逗号（row 0 实际炸点格式）。"""
        text = '{\n  "claims": [\n    {"type": "entity", "text": "营收增长"},\n    {"type": "metric", "text": "PE 12"},\n  ]\n}'
        result = parse_json_response(text)
        assert result["claims"][1]["text"] == "PE 12"

    def test_object_trailing_comma(self):
        """对象末键后尾逗号。"""
        result = parse_json_response('{"a": 1, "b": 2,}')
        assert result == {"a": 1, "b": 2}

    def test_nested_trailing_commas(self):
        """嵌套结构混合尾逗号。"""
        text = '{"list": [{"x": 1,}, {"y": [2, 3,],},], "tail": true,}'
        result = parse_json_response(text)
        assert result["list"][1]["y"] == [2, 3]
        assert result["tail"] is True

    def test_markdown_wrapped_trailing_comma(self):
        """markdown 代码块包裹 + 尾逗号（LLM 常见输出组合）。"""
        text = '结论如下：\n```json\n{"decision": "buy", "confidence": 0.8,}\n```'
        result = parse_json_response(text)
        assert result["decision"] == "buy"

    def test_valid_json_unaffected(self):
        """正常 JSON 不受容错逻辑影响。"""
        result = parse_json_response('{"a": [1, 2], "b": {"c": 3}}')
        assert result == {"a": [1, 2], "b": {"c": 3}}


class TestParseErrorsStillRaise:
    def test_no_json_raises(self):
        """无 JSON 内容仍应抛 JSONDecodeError（上游降级依赖此信号）。"""
        with pytest.raises(json.JSONDecodeError):
            parse_json_response("纯文本回答，没有任何结构。")

    def test_empty_string_raises(self):
        """空输出（reasoning 吃满配额场景）抛 JSONDecodeError 而非返回垃圾。"""
        with pytest.raises(json.JSONDecodeError):
            parse_json_response("")


class TestUnescapedInnerQuotes:
    """r1 实验实证（中芯 fundamental 第 3 代）：GLM 在字符串值里输出未转义的成对引号
    `"summary": "中芯国际基本面呈"低盈利+高扩张"格局…"` → 解析炸 → 分析师降级兜底
    覆盖了前两代好报告。字符串内的引号若后面紧跟的不是结构字符（, } ] :），
    就不是终止符，应视作内嵌引号转义后再解析。
    """

    def test_inner_quotes_in_string_value(self):
        text = '{"agent_name": "fundamental", "summary": "中芯国际基本面呈"低盈利+高扩张"格局：营收增长16.5%", "n": 1}'
        result = parse_json_response(text)
        assert result["summary"] == '中芯国际基本面呈"低盈利+高扩张"格局：营收增长16.5%'
        assert result["n"] == 1

    def test_real_shape_fenced_multiline_mixed_escaping(self):
        """同一响应里既有未转义内嵌引号也有正确转义的 \\"（r1 原样形态）。"""
        text = (
            "```json\n{\n"
            '  "agent_name": "fundamental",\n'
            '  "summary": "中芯国际基本面呈"低盈利+高扩张"格局：ROE仅3.4%。",\n'
            '  "plain_conclusion": "偏中性谨慎",\n'
            '  "key_findings": ["本质是\\"重投入、低回报\\"模式"],\n'
            '  "claims": [],\n'
            '  "markdown": "## 基本面"\n'
            "}\n```"
        )
        result = parse_json_response(text)
        assert result["summary"].startswith('中芯国际基本面呈"低盈利+高扩张"格局')
        assert result["key_findings"] == ['本质是"重投入、低回报"模式']
        assert result["plain_conclusion"] == "偏中性谨慎"

    def test_escaped_quotes_and_valid_json_unaffected(self):
        assert parse_json_response('{"a": "he said \\"hi\\"", "b": 2}') == {
            "a": 'he said "hi"',
            "b": 2,
        }
        assert parse_json_response('{"a": "x, y", "b": [1, 2]}') == {"a": "x, y", "b": [1, 2]}
