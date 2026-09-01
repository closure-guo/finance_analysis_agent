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
from unittest.mock import MagicMock, patch

import pandas as pd

from finance_agent.nodes.analysts import (
    _build_fundamental_context,
    _build_macro_context,
    _build_technical_context,
    _retry_feedback_section,
    _series_semantic_header,
    technical_analyst,
)


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


class TestAnalystSpanMetadata:
    """解析降级 / 枚举改写路径的 span metadata（trace-observability Task 6）。

    降级与改写此前只记日志，trace 不可见；本组测试锁定 update_current_span
    写入的 metadata 与 level，使静默修复在 Langfuse trace 可见。
    """

    def test_parse_degraded_marks_span(self, monkeypatch):
        """JSON 解析失败降级时，span metadata 记 parse_degraded，level=WARNING。"""
        from finance_agent.nodes.analysts import _parse_analyst_report

        captured = {}

        def _fake_update(metadata=None, level=None):
            captured["metadata"] = metadata
            captured["level"] = level

        monkeypatch.setattr("finance_agent.nodes.analysts.update_current_span", _fake_update)

        # 喂非法 JSON 触发降级
        report = _parse_analyst_report("not a json {{{", "technical")
        assert report.parse_degraded is True
        assert captured["metadata"]["degradation"] == "parse_degraded"
        assert captured["level"] == "WARNING"

    def test_sanitize_claims_marks_span(self, monkeypatch):
        """非法枚举被改写时，span metadata 记 sanitize_claims。"""
        from finance_agent.nodes.analysts import _sanitize_claims

        captured = []

        def _fake_update(metadata=None, level=None):
            captured.append({"metadata": metadata, "level": level})

        monkeypatch.setattr("finance_agent.nodes.analysts.update_current_span", _fake_update)

        _sanitize_claims(
            {"claims": [{"claim_type": "非法类型", "source_type": "data"}]}, "technical"
        )
        # 断言至少一次 sanitize_claims 记录
        assert any(
            c["metadata"] and c["metadata"].get("degradation") == "sanitize_claims"
            for c in captured
        )
        assert all(c["level"] == "WARNING" for c in captured if c["metadata"])

    def test_trace_errors_do_not_block_degradation(self):
        """Langfuse client 抛异常时，解析降级流程仍正常完成（降级不阻断业务）。"""
        from finance_agent.nodes.analysts import _parse_analyst_report

        mockClient = MagicMock()
        mockClient.update_current_span.side_effect = RuntimeError("langfuse down")
        with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient):
            report = _parse_analyst_report("坏响应", "technical")
        # 埋点失败被 update_current_span 吞掉，业务照常降级产出报告
        assert report.parse_degraded is True
        assert report.claims == []


class TestTechnicalContextBudget:
    """analyst-context-budget delta：技术指标序列裁剪为最近 60 期。

    线上事故（601700 深研）：250 期全窗口指标 JSON 进 prompt，
    technical_analyst 单次 LLM 调用 11.5~14 分钟。
    """

    def _indicators(self, n: int) -> dict:
        full = [None] * 59 + [float(i) for i in range(n)]  # 前 59 期预热 null
        series = full[:n]
        return {
            "MA": {"5": list(series), "10": list(series)},
            "MACD": {"DIF": list(series), "DEA": list(series), "histogram": list(series)},
            "RSI": {"14": list(series)},
        }

    def test_full_window_series_trimmed_to_60(self):
        """250 期序列裁剪为最近 60 期，context 含窗口说明。"""
        from finance_agent.nodes.analysts import _build_technical_context

        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "technical_indicators": self._indicators(250),
        }
        ctx = _build_technical_context(state)

        assert "更早历史已省略" in ctx, "context 必须携带窗口说明，避免 LLM 误认截断窗口为全部历史"
        payload = ctx.split("技术指标数据", 1)[1].split(":\n", 1)[1]
        data = json.loads(payload)
        assert len(data["MA"]["5"]) == 60
        assert len(data["MACD"]["DIF"]) == 60
        # 序列值规则：index i（>=59）的值为 i-59；最近 60 期首元素为 index 190 → 131.0
        assert data["MA"]["5"][0] == 131.0

    def test_short_window_series_kept_intact(self):
        """不足 60 期的窗口保持完整。"""
        from finance_agent.nodes.analysts import _build_technical_context

        state = {
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "technical_indicators": self._indicators(45),
        }
        ctx = _build_technical_context(state)
        payload = ctx.split("技术指标数据", 1)[1].split(":\n", 1)[1]
        data = json.loads(payload)
        assert len(data["MA"]["5"]) == 45
        assert len(data["RSI"]["14"]) == 45

    def test_missing_indicators_keeps_fallback(self):
        """无 technical_indicators 时 context 不含指标段（既有兜底）。"""
        from finance_agent.nodes.analysts import _build_technical_context

        ctx = _build_technical_context({"stock_name": "X", "stock_code": "1"})
        assert "技术指标数据" not in ctx


class TestTechnicalContextArrayOrder:
    def test_context_declares_ascending_order_tail_latest(self):
        """序列数组为时间正序（旧→新），末尾为最新一期（incident 022 第四类疾病）。"""
        from finance_agent.nodes.analysts import _build_technical_context

        ctx = _build_technical_context(
            {
                "stock_name": "中际旭创",
                "stock_code": "300308",
                "technical_indicators": {
                    "MA": {"5": [1211.36, 858.318]},
                    "MACD": {"DIF": [96.64, -44.09]},
                    "RSI": {"14": [62.63, 41.56]},
                    "BOLL": {
                        "upper": [1282.05, 1016.9],
                        "middle": [1100.09, 915.36],
                        "lower": [918.14, 813.82],
                    },
                    "KDJ": {"K": [70.3, 19.57], "D": [78.28, 27.11], "J": [54.35, 4.49]},
                },
            }
        )
        assert "时间正序" in ctx and "末尾" in ctx and "最新" in ctx


class TestRetryFeedbackSection:
    def test_no_feedback_returns_empty(self):
        assert _retry_feedback_section({}, "fundamental") == ""

    def test_feedback_renders_failed_claims(self):
        state = {
            "citation_retry_feedback": {
                "fundamental": [
                    {
                        "field_ref": "solvency_metrics.资产负债率.2023",
                        "stated_value": 99.0,
                        "ground_truth": 38.0,
                        "delta": 61.0,
                        "interpretation": "2023 年资产负债率 99%",
                    }
                ]
            }
        }
        section = _retry_feedback_section(state, "fundamental")
        assert "上轮引用校验失败" in section
        assert "solvency_metrics.资产负债率.2023" in section
        assert "38.0" in section  # ground_truth 必须随反馈给出（与旧盲目重跑的关键区别）
        assert "99.0" in section

    def test_feedback_scoped_to_agent(self):
        state = {
            "citation_retry_feedback": {
                "macro": [
                    {
                        "field_ref": "x",
                        "stated_value": 1,
                        "ground_truth": 2,
                        "delta": 1,
                        "interpretation": "y",
                    }
                ]
            }
        }
        assert _retry_feedback_section(state, "fundamental") == ""


class TestSeriesSemanticHeader:
    def test_header_format(self):
        h = _series_semantic_header("时间正序(旧→新)", "index -1 = 最新交易日(2026-08-28)", 60)
        assert h == "# 序列语义: 时间正序(旧→新), index -1 = 最新交易日(2026-08-28), 共60期"

    def test_technical_header_declares_direction_and_latest_date(self):
        """incident 022 修复：语义头机生，期次与 state 实际数据一致。"""
        state = {
            "stock_name": "中际旭创",
            "stock_code": "300308",
            "kline": pd.DataFrame(
                {"日期": [f"2026-08-{d:02d}" for d in range(1, 29)], "收盘": [100.0] * 28}
            ),
            "technical_indicators": {"MA": {"5": [100.0 + i for i in range(28)]}},
        }
        ctx = _build_technical_context(state)
        assert "# 序列语义: 时间正序(旧→新)" in ctx
        assert "index -1 = 最新交易日(2026-08-28)" in ctx
        assert "共28期" in ctx
        # 与校验语义一致：列表末尾为最新一期（既有负索引声明仍在）
        assert "-1=最新一期" in ctx

    def test_technical_header_without_kline_degrades(self):
        """kline 缺失 → 方向声明保留，日期省略（不编造期次）。"""
        state = {"technical_indicators": {"MA": {"5": [1.0, 2.0]}}}
        ctx = _build_technical_context(state)
        assert "时间正序(旧→新)" in ctx
        assert "最新交易日" not in ctx

    def test_macro_header_declares_descending_and_latest_month(self):
        state = {
            "stock_name": "x",
            "stock_code": "x",
            "macro_indicators": {
                "cpi": {
                    "records": [
                        {"月份": "2026年07月份", "全国-同比增长": 0.4},
                        {"月份": "2026年06月份", "全国-同比增长": 0.5},
                    ],
                    "freshness": "fresh",
                }
            },
        }
        ctx = _build_macro_context(state)
        assert "# 序列语义: 时间降序(新→旧)" in ctx
        assert "index 0 = 最新一期(2026年07月份)" in ctx
        assert "共2期" in ctx

    def test_fundamental_headers(self):
        """报表段声明降序 + 首行最新期；季度趋势段声明 index 0 最新。"""
        df = pd.DataFrame(
            {"报告日": ["20251231", "20241231", "20231231"], "营业总收入": [1.0, 2.0, 3.0]}
        )
        state = {
            "stock_name": "x",
            "stock_code": "x",
            "balance_sheet": df,
            "income_statement": df,
            "cash_flow_statement": df,
            "quarterly_trend": {
                "quarters": ["2025Q4", "2025Q3"],
                "net_profit": [1.0, 2.0],
                "qoq": [1.0, 2.0],
                "yoy": [1.0, 2.0],
                "warnings": [],
            },
        }
        ctx = _build_fundamental_context(state)
        assert "行按报告期降序(新→旧), 首行 = 最新报告期(20251231)" in ctx
        assert "# 序列语义: 时间降序(新→旧), index 0 = 最新季度(2025Q4), 共2期" in ctx


class TestTechnicalHeaderDatetime:
    def test_kline_datetime64_header_iso_date(self):
        """机生语义头对 datetime64 日期列渲染 ISO 日期（与校验器解析口径一致）。"""
        import pandas as pd

        from finance_agent.nodes.analysts import _build_technical_context

        ctx = _build_technical_context(
            {
                "stock_name": "测试",
                "stock_code": "000001",
                "kline": pd.DataFrame({"日期": pd.to_datetime(["2026-08-27", "2026-08-28"])}),
                "technical_indicators": {"RSI": {"14": [62.63, 41.56]}},
            }
        )
        assert "最新交易日(2026-08-28)" in ctx
