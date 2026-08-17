# tests/llm/test_contracts.py
"""结构化输出合同测试（delta Task 3.1）。

extract_json（纯解析）+ parse_with_contract（validate→repair→typed error）。
覆盖实战格式瑕疵：尾逗号（incident 017）、单引号噪声、fence 包裹、空输出。
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from finance_agent.llm.contracts import extract_json, parse_with_contract
from finance_agent.llm.errors import OutputContractError


class _Decision(BaseModel):
    decision: str
    confidence: float


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_fence(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_surrounding_noise(self):
        assert extract_json('结论如下：\n\n{"a": 1}') == {"a": 1}

    def test_trailing_comma_array(self):
        """尾逗号直接清理解析（incident 017 实战炸点格式）。"""
        text = '{\n  "claims": [\n    {"x": 1},\n    {"y": 2},\n  ]\n}'
        assert extract_json(text) == {"claims": [{"x": 1}, {"y": 2}]}

    def test_trailing_comma_object(self):
        assert extract_json('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}

    def test_empty_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json("")

    def test_plain_text_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json("我认为风险可控，无需结构化。")


class TestParseWithContract:
    def test_valid_first_try_no_repair(self):
        calls: list[str] = []

        def _repair(excerpt, error):
            calls.append(excerpt)
            raise AssertionError("不应触发 repair")

        result = parse_with_contract(
            '{"decision": "buy", "confidence": 0.8}',
            schema=_Decision,
            repair=_repair,
        )
        assert result.decision == "buy"
        assert calls == []

    def test_bad_then_repair_succeeds(self):
        """坏输出 → repair 重试成功（repair 返回修正文本）。"""
        repair_calls: list[tuple[str, str]] = []

        def _repair(excerpt: str, error: str) -> str:
            repair_calls.append((excerpt, error))
            return '{"decision": "hold", "confidence": 0.5}'

        result = parse_with_contract(
            '{"decision": "买买买", "confidence": "高"}',
            schema=_Decision,
            repair=_repair,
        )
        assert result.decision == "hold"
        assert len(repair_calls) == 1
        assert "confidence" in repair_calls[0][1]  # 错误信息含失败字段

    def test_repair_exhausted_raises_contract_error(self):
        """repair 后仍失败 → OutputContractError 带 raw_excerpt。"""

        def _repair(excerpt: str, error: str) -> str:
            return "还是不是 JSON"

        with pytest.raises(OutputContractError) as ei:
            parse_with_contract("原始输出", schema=_Decision, repair=_repair, max_repairs=2)
        assert "原始输出" in ei.value.raw_excerpt

    def test_extract_fail_triggers_repair(self):
        """纯文本（无 JSON）触发 repair 而非直接抛。"""
        repair_calls: list[str] = []

        def _repair(excerpt: str, error: str) -> str:
            repair_calls.append(excerpt)
            return '{"decision": "buy", "confidence": 0.9}'

        result = parse_with_contract("我认为风险可控。", schema=_Decision, repair=_repair)
        assert result.decision == "buy"
        assert repair_calls == ["我认为风险可控。"]

    def test_repair_none_means_no_retry(self):
        """未提供 repair 函数 → 直接抛合同错误（调用方选择不重试）。"""
        with pytest.raises(OutputContractError):
            parse_with_contract("坏输出", schema=_Decision, repair=None)
