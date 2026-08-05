"""TDD tests for nodes/analysts.py — Layer I 分析师 Agent。

Agent 行为：
1. 接收 state（含 PREP 数据）
2. 构建 prompt context
3. 调用 LLM（mocked）
4. 解析 JSON 响应为 AnalystReport
5. 返回 state 更新
"""

import json
import logging
from unittest.mock import patch

from finance_agent.nodes.analysts import technical_analyst


def _mock_llm_response() -> str:
    """模拟 LLM 返回的 AnalystReport JSON。"""
    return json.dumps(
        {
            "agent_name": "technical",
            "summary": "技术面分析显示短期趋势向上",
            "key_findings": ["MA5 上穿 MA20", "MACD 金叉"],
            "claims": [
                {
                    "claim_type": "numerical",
                    "source_type": "data",
                    "field_ref": "technical_indicators.MA.5.4",
                    "stated_value": 13.0,
                    "interpretation": "MA5 为 13.0",
                }
            ],
            "markdown": "## 技术面分析\n短期趋势向上。",
        },
        ensure_ascii=False,
    )


class TestTechnicalAnalyst:
    """Layer I 技术面分析师 Agent 测试。"""

    @patch("finance_agent.nodes.analysts.call_llm_streaming")
    def test_produces_analyst_report(self, mock_llm):
        """技术分析师返回 AnalystReport 结构化输出。"""
        mock_llm.return_value = _mock_llm_response()
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "technical_indicators": {
                "MA": {"5": [None, None, None, None, 13.0, 14.0]},
            },
        }
        result = technical_analyst(state)

        assert "analyst_reports" in result
        report = result["analyst_reports"]["technical"]
        assert report.agent_name == "technical"
        assert len(report.claims) == 1
        assert report.claims[0].stated_value == 13.0

    @patch("finance_agent.nodes.analysts.call_llm_streaming")
    def test_llm_response_with_code_block(self, mock_llm):
        """LLM 返回 markdown 代码块包裹的 JSON 也能正确解析。"""
        mock_llm.return_value = f"```json\n{_mock_llm_response()}\n```"
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "technical_indicators": {"MA": {"5": [None, None, None, None, 13.0]}},
        }
        result = technical_analyst(state)
        report = result["analyst_reports"]["technical"]
        assert report.agent_name == "technical"


class TestAnalystDegradationObservability:
    """解析降级与字段改写的可观测性（harden-llm-output-validation）。

    加固前降级与改写完全静默：解析失败产出 claims=[] 的报告，
    而零 claim 会使引用校验 all_passed=True（citation.py 的 failed == 0），
    即解析失败反而让校验「通过」，属隐蔽的静默失败。
    """

    _STATE = {
        "stock_name": "贵州茅台",
        "stock_code": "600519",
        "technical_indicators": {"MA": {"5": [None, None, None, None, 13.0]}},
    }

    @patch("finance_agent.nodes.analysts.call_llm_streaming")
    def test_malformed_json_logs_warning(self, mock_llm, caplog):
        """解析失败记录 WARNING 日志，包含节点名。"""
        mock_llm.return_value = "这不是 JSON，只是一段自由文本"
        with caplog.at_level(logging.WARNING):
            technical_analyst(dict(self._STATE))
        assert any(
            r.levelno == logging.WARNING and "technical" in r.getMessage() for r in caplog.records
        ), f"未记录含节点名的 WARNING：{[r.getMessage() for r in caplog.records]}"

    @patch("finance_agent.nodes.analysts.call_llm_streaming")
    def test_degraded_report_carries_marker(self, mock_llm):
        """降级报告携带可识别标记，使下游能区分「解析失败的零 claim」与「正常的零 claim」。"""
        mock_llm.return_value = "坏响应"
        report = technical_analyst(dict(self._STATE))["analyst_reports"]["technical"]
        assert report.parse_degraded is True
        assert report.claims == []

    @patch("finance_agent.nodes.analysts.call_llm_streaming")
    def test_successful_parse_has_no_degraded_marker(self, mock_llm):
        """正常解析的报告不带降级标记（与降级路径可区分）。"""
        mock_llm.return_value = _mock_llm_response()
        report = technical_analyst(dict(self._STATE))["analyst_reports"]["technical"]
        assert report.parse_degraded is False

    @patch("finance_agent.nodes.analysts.call_llm_streaming")
    def test_invalid_claim_type_logs_warning(self, mock_llm, caplog):
        """非法 claim_type 改写为 entity 时记录 WARNING（含原值与改写后值）。"""
        payload = json.loads(_mock_llm_response())
        payload["claims"][0]["claim_type"] = "textual"  # 不在 _VALID_CLAIM_TYPES 内
        mock_llm.return_value = json.dumps(payload, ensure_ascii=False)

        with caplog.at_level(logging.WARNING):
            report = technical_analyst(dict(self._STATE))["analyst_reports"]["technical"]

        assert report.claims[0].claim_type == "entity"  # 保留既有改写行为
        messages = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
        assert "textual" in messages and "entity" in messages, (
            f"WARNING 未含原值与改写值：{messages}"
        )

    @patch("finance_agent.nodes.analysts.call_llm_streaming")
    def test_invalid_source_type_logs_warning(self, mock_llm, caplog):
        """非法 source_type 改写为 data 时记录 WARNING（含原值与改写后值）。"""
        payload = json.loads(_mock_llm_response())
        payload["claims"][0]["source_type"] = "hearsay"  # 不在 _VALID_SOURCE_TYPES 内
        mock_llm.return_value = json.dumps(payload, ensure_ascii=False)

        with caplog.at_level(logging.WARNING):
            report = technical_analyst(dict(self._STATE))["analyst_reports"]["technical"]

        assert report.claims[0].source_type == "data"  # 保留既有改写行为
        messages = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
        assert "hearsay" in messages and "data" in messages, f"WARNING 未含原值与改写值：{messages}"
