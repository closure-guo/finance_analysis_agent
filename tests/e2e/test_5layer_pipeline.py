"""端到端测试: 5 层架构图全流程（真实 LLM + 真实 AKShare 数据）。

验证 build_5layer_graph() 的完整图流：
  PREP → Layer I → Citation → Layer II → Layer III → Layer IV → Layer V → Report

运行方式：
    set DEEPSEEK_API_KEY=your_key
    uv run pytest tests/e2e/test_5layer_pipeline.py -s
"""

import os

import pytest

from finance_agent.graph import build_5layer_graph

pytestmark = pytest.mark.skipif(
    not (os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")),
    reason="E2E 测试需要真实 LLM，请设置 DEEPSEEK_API_KEY 或 LLM_API_KEY 环境变量",
)


STOCK_CODE = "600519"
STOCK_NAME = "贵州茅台"


class Test5LayerPipelineE2E:
    """5 层架构图端到端测试（真实链路，单次 graph 调用验证全部维度）。"""

    def test_full_pipeline_produces_report(self):
        """完整 5 层流程：PREP → 5 层 Agent → 报告生成，验证各层产出。"""
        graph = build_5layer_graph()
        initial_state = {
            "stock_code": STOCK_CODE,
            "stock_name": STOCK_NAME,
        }
        result = graph.invoke(initial_state, config={"recursion_limit": 100})

        # ── 最终报告 ──
        assert result is not None
        assert "final_report" in result
        assert STOCK_NAME in result["final_report"]

        # ── Layer I：分析师报告 ──
        assert "analyst_reports" in result
        assert "technical" in result["analyst_reports"]

        # ── Layer II：多空辩论 ──
        assert "debate_history" in result
        # 2 轮 × 2 方 = 4 条消息（轮次由 graph 配置决定，非 LLM 输出）
        assert len(result["debate_history"]) == 4

        # ── Layer III/IV：交易决策 ──
        assert "final_trade_decision" in result
        decision = result["final_trade_decision"]
        assert decision.action in ("buy", "sell", "hold", "watch")

        # ── Layer V：基金经理决策 ──
        assert "fund_manager_decision" in result
        assert result["fund_manager_decision"] in ("approve", "reject", "revise")
