"""TDD tests for nodes/report.py — 5 层架构报告生成节点。

节点行为：
1. 从 state 读取 5 层 Agent 输出
2. 组装为结构化 Markdown 报告
3. 返回 {"final_report": markdown}
"""

from finance_agent.models import AnalystReport, TradeDecision
from finance_agent.nodes.report import generate_report


class TestGenerateReport:
    """报告生成节点测试。"""

    def test_report_contains_analyst_summaries(self):
        """报告包含各分析师的摘要。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "analyst_reports": {
                "fundamental": AnalystReport(
                    agent_name="fundamental",
                    summary="基本面强劲",
                    key_findings=["ROE 28.33%"],
                    claims=[],
                    markdown="## 基本面分析\n...",
                ),
                "technical": AnalystReport(
                    agent_name="technical",
                    summary="技术面偏多",
                    key_findings=["MA5 上穿 MA20"],
                    claims=[],
                    markdown="## 技术面分析\n...",
                ),
            },
        }
        result = generate_report(state)
        report = result["final_report"]
        assert "基本面强劲" in report
        assert "技术面偏多" in report

    def test_report_contains_trade_decision(self):
        """报告包含交易决策。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "final_trade_decision": TradeDecision(
                action="buy",
                confidence=0.75,
                reasoning="ROE 持续高于 15%",
            ),
        }
        result = generate_report(state)
        report = result["final_report"]
        assert "buy" in report
        assert "75%" in report

    def test_report_contains_fund_manager_decision(self):
        """报告包含基金经理决策。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "fund_manager_decision": "approve",
        }
        result = generate_report(state)
        report = result["final_report"]
        assert "approve" in report

    def test_report_contains_stock_header(self):
        """报告包含股票名称和代码。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
        }
        result = generate_report(state)
        report = result["final_report"]
        assert "贵州茅台" in report
        assert "600519" in report
