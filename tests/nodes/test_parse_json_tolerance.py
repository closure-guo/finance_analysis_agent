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
