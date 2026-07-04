"""TDD tests for nodes/analysts.py — Layer I 分析师 Agent。

Agent 行为：
1. 接收 state（含 PREP 数据）
2. 构建 prompt context
3. 调用 LLM（mocked）
4. 解析 JSON 响应为 AnalystReport
5. 返回 state 更新
"""

import json
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

    @patch("finance_agent.nodes.analysts.call_llm")
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

    @patch("finance_agent.nodes.analysts.call_llm")
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
