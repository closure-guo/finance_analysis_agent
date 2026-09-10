"""TDD tests for nodes/report.py — 5 层架构报告生成节点。

节点行为：
1. 从 state 读取 5 层 Agent 输出
2. 组装为结构化 Markdown 报告
3. 返回 {"final_report": markdown}
"""

from unittest.mock import patch

import pytest

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
                    plain_conclusion="结论：基本面强劲",
                    key_findings=["ROE 28.33%"],
                    claims=[],
                    markdown="## 基本面分析\n...",
                ),
                "technical": AnalystReport(
                    agent_name="technical",
                    summary="技术面偏多",
                    plain_conclusion="结论：技术面偏多",
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
        """报告包含基金经理决策（以中文标注呈现，非原始英文枚举值）。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "fund_manager_decision": "approve",
        }
        result = generate_report(state)
        report = result["final_report"]
        assert "审批通过" in report

    @pytest.mark.parametrize(
        ("decision", "expected"),
        [
            ("approve", "审批通过"),
            ("reject", "未通过审批"),
            ("return", "退回"),
        ],
    )
    def test_fund_manager_decision_chinese_annotation(self, decision, expected):
        """三种决策各自渲染为语义明确的中文标注（ADR-0011 Layer V）。

        加固前 report.py 只输出 `**reject**`，读者无法从报告识别「未通过审批」。
        """
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "fund_manager_decision": decision,
        }
        report = generate_report(state)["final_report"]
        assert expected in report

    def test_focus_summary_generated_without_focus(self):
        """D3（3.1）：focus 为空时仍生成聚焦摘要（fallback 结构化拼接）并落 state——
        研究聚焦是无条件产物，不再依赖用户填写 focus。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "fund_manager_decision": "approve",
            "research_manager_conclusion": "中性偏谨慎：证据均衡，等待右侧信号。",
        }
        result = generate_report(state)
        assert result.get("focus_summary"), "focus 为空也应有聚焦摘要（fallback）"

    def test_focus_summary_from_llm_landed_in_state(self):
        """D3：LLM 生成的聚焦摘要 SHALL 写入 state["focus_summary"]（judge 变量直取源）。"""
        from finance_agent.nodes import report as report_mod

        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "focus": "全面分析贵州茅台的投资价值",
            "research_manager_conclusion": "中性：证据均衡。",
        }
        with patch.object(report_mod, "complete_text") as mock_ct:
            mock_ct.return_value = ("聚焦摘要：多空均衡，建议观望。", {})
            result = generate_report(state)
        assert result.get("focus_summary") == "聚焦摘要：多空均衡，建议观望。"
        assert "## 研究聚焦" in result["final_report"]

    def test_fm_action_and_ruling_action_shown_side_by_side(self):
        """D1：FM 操作定性（action/置信度）与裁决 action 并排展示——
        「批准的是什么方案」直接可见，方向相悖时矛盾自明（agent-node-contracts）。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "fund_manager_decision": "approve",
            "fund_manager_action": "watch",
            "fund_manager_confidence": 0.55,
            "final_trade_decision": {"action": "watch"},
        }
        report = generate_report(state)["final_report"]
        assert "操作定性 watch" in report
        assert "置信度 0.55" in report
        assert "裁决: watch" in report

    def test_fm_action_omitted_when_absent(self):
        """历史 state 无 action/confidence 时保持旧行为（仅中文标注+理由）。"""
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "fund_manager_decision": "approve",
        }
        report = generate_report(state)["final_report"]
        assert "审批通过" in report
        assert "操作定性" not in report

    def test_report_tolerates_legacy_invalid_decision(self):
        """历史非法决策值不应让报告生成抛错，回退显示原始值。

        读路径不因历史数据失败（harden-llm-output-validation Migration Plan）。
        """
        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "fund_manager_decision": "revise",  # 加固前可能写入的非法值
        }
        report = generate_report(state)["final_report"]
        assert "revise" in report

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

    def test_focus_reorders_and_folds_sections(self, monkeypatch):
        """focus 命中维度时：重点分析师前置并标星，非重点折叠，出现研究聚焦摘要。"""
        from finance_agent.nodes import report as report_mod

        # 打桩 LLM 摘要调用（complete_text 返回 (text, metadata) 元组），避免真实请求
        monkeypatch.setattr(report_mod, "complete_text", lambda *a, **k: ("围绕估值的摘要文本", {}))

        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "focus": "估值是否合理，中长期持有",
            "analyst_reports": {
                "fundamental": AnalystReport(
                    agent_name="fundamental",
                    summary="基本面强劲",
                    plain_conclusion="结论：基本面强劲",
                    key_findings=["ROE 28.33%"],
                    claims=[],
                    markdown="",
                ),
                "technical": AnalystReport(
                    agent_name="technical",
                    summary="技术面偏多",
                    plain_conclusion="结论：技术面偏多",
                    key_findings=["MA5 上穿 MA20"],
                    claims=[],
                    markdown="",
                ),
            },
        }
        result = generate_report(state)
        report = result["final_report"]

        # 研究聚焦摘要出现
        assert "研究聚焦" in report
        assert "围绕估值的摘要文本" in report
        # 报告头部标注研究聚焦
        assert "研究聚焦: 估值是否合理" in report
        # fundamental（命中 valuation/growth）为重点，标星且出现在 technical 之前
        assert report.index("fundamental") < report.index("technical")
        assert "★ 重点" in report
        # technical（未命中）被折叠
        assert "<details>" in report


class TestFundManagerReasoningRendered:
    """refine #111：报告渲染 FM 审批理由（在场时）。"""

    def test_report_contains_fm_reasoning(self):
        state = {
            "stock_code": "600519",
            "final_trade_decision": {"action": "watch", "confidence": 0.5, "reasoning": "x"},
            "fund_manager_decision": "reject",
            "fund_manager_decision_reasoning": "最大回撤38.8%超出审慎投资标准",
        }
        md = generate_report(state)["final_report"]
        assert "最大回撤38.8%超出审慎投资标准" in md

    def test_no_reasoning_falls_back_to_annotation_only(self):
        state = {
            "stock_code": "600519",
            "final_trade_decision": {"action": "watch", "confidence": 0.5, "reasoning": "x"},
            "fund_manager_decision": "approve",
        }
        md = generate_report(state)["final_report"]
        assert "审批通过" in md


class TestDeriveFocusFromQuery:
    """D4：focus 兜底——query 提取关注点关键词合成弱 focus。"""

    def test_extracts_keywords_from_query(self):
        from finance_agent.nodes.report import derive_focus_from_query

        focus = derive_focus_from_query("分析贵州茅台当前适不适合作为长期持有股买入")
        assert focus, "应提取出关键词"
        assert "长期" in focus or "持有" in focus

    def test_zero_hit_returns_empty(self):
        from finance_agent.nodes.report import derive_focus_from_query

        assert derive_focus_from_query("帮我看看这只股票") == ""

    def test_empty_query_returns_empty(self):
        from finance_agent.nodes.report import derive_focus_from_query

        assert derive_focus_from_query("") == ""
