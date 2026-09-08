"""add-toolcall-evaluation：轨迹提取 + 四维评估 测试（fixtures 离线）。"""

from evals.toolcall.measure import (
    ToolCallRecord,
    allow_set_check,
    efficiency_issues,
    evaluate,
    extract_toolcalls,
    failure_recovery,
    run_offline,
    validate_params,
)


def _span(name, latency=10.0, error=None, call=None):
    o = {"name": f"tool_call:{name}", "latency": latency, "metadata": {}}
    if error:
        o["metadata"]["tool_error"] = error
    if call is not None:
        o["input"] = {"call": call}
    return o


def _trace(observations, name="react_loop", ts="2026-09-04T10:00:00Z"):
    return {"id": "t1", "name": name, "timestamp": ts, "observations": observations}


class TestExtract:
    def test_tool_prefix_spans_extracted(self):
        t = _trace(
            [_span("web_search", call={"query": "热门股"}), _span("search_stock", error="boom")]
        )
        calls = extract_toolcalls(t)
        assert [c.name for c in calls] == ["web_search", "search_stock"]
        assert calls[0].latency_ms == 10.0
        assert calls[0].args_hint == {"query": "热门股"}
        assert calls[1].error == "boom"

    def test_non_tool_observations_ignored(self):
        t = _trace([{"name": "some-generation", "type": "GENERATION"}, _span("web_search")])
        assert len(extract_toolcalls(t)) == 1

    def test_empty(self):
        assert extract_toolcalls({"observations": []}) == []


class TestAllowSet:
    def test_illegal_name_detected(self):
        calls = [ToolCallRecord("web_search"), ToolCallRecord("evil_tool")]
        assert [v["name"] for v in allow_set_check(calls)] == ["evil_tool"]

    def test_all_allowed(self):
        calls = [ToolCallRecord("web_search"), ToolCallRecord("search_stock")]
        assert allow_set_check(calls) == []


class TestParams:
    def test_missing_required(self):
        calls = [
            ToolCallRecord("web_search", args_hint={"query": "x"}),
            ToolCallRecord("search_stock", args_hint={"stock_code": "600519"}),
            ToolCallRecord("search_stock", args_hint={}),
        ]
        required = {"web_search": ["query"], "search_stock": ["stock_code"]}
        violations = validate_params(calls, required)
        assert len(violations) == 1
        assert violations[0]["name"] == "search_stock"
        assert violations[0]["missing"] == ["stock_code"]

    def test_no_args_hint_skipped(self):
        # trace 无 args 时不误判（数据源限制）
        assert validate_params([ToolCallRecord("web_search")], {"web_search": ["query"]}) == []


class TestEfficiency:
    def test_consecutive_duplicate_flagged(self):
        calls = [ToolCallRecord("a"), ToolCallRecord("a"), ToolCallRecord("b"), ToolCallRecord("b")]
        issues = efficiency_issues(calls)
        assert [i["index"] for i in issues] == [1, 3]

    def test_alternating_not_flagged(self):
        calls = [ToolCallRecord("a"), ToolCallRecord("b"), ToolCallRecord("a")]
        assert efficiency_issues(calls) == []


class TestRecovery:
    def test_error_with_switch_recovered(self):
        calls = [ToolCallRecord("a", error="x"), ToolCallRecord("b")]
        assert failure_recovery(calls) == []

    def test_error_at_end_unrecovered(self):
        calls = [ToolCallRecord("a"), ToolCallRecord("b", error="x")]
        assert len(failure_recovery(calls)) == 1

    def test_repeated_same_tool_after_error_unrecovered(self):
        calls = [ToolCallRecord("a", error="x"), ToolCallRecord("a")]
        assert len(failure_recovery(calls)) == 1


class TestEvaluate:
    def test_golden_sequence_zero_violations(self):
        traces = [
            _trace(
                [
                    _span("web_search", call={"query": "热点"}),
                    _span("search_stock", call={"stock_code": "600519"}),
                ]
            ),
            _trace([_span("run_deep_analysis", call={"stock_code": "600519"})]),
        ]
        report, sequences = evaluate(
            traces,
            required_by_tool={
                "web_search": ["query"],
                "search_stock": ["stock_code"],
                "run_deep_analysis": ["stock_code"],
            },
        )
        assert report.total_calls == 3
        assert report.per_tool["web_search"] == 1
        v = report.violations
        assert not v.allow_set and not v.params and not v.redundancy and not v.recovery
        assert len(sequences) == 2

    def test_adversarial_all_violations(self):
        traces = [
            _trace(
                [
                    _span("evil_tool"),
                    _span("web_search", call={}),
                    _span("web_search", call={"query": "x"}),
                    _span("search_stock", error="boom"),
                ]
            ),
        ]
        report, _ = evaluate(traces)
        v = report.violations
        assert len(v.allow_set) == 1
        assert len(v.redundancy) == 1  # 连续 web_search
        assert len(v.recovery) == 1  # error 后无不同工具

    def test_run_offline_keys(self):
        result = run_offline([_trace([_span("web_search")])])
        assert result["report"].total_calls == 1
        assert len(result["sequences"]) == 1
