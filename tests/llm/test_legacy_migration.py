"""migrate-off-legacy-llm-shim Task 1: 4 个 call_llm 调用方迁移测试。

mock 目标：各调用方模块内的 ``complete_text``（模块级 import 绑定），断言
legacy 语义逐条复刻：
- quick=True → purpose="quick"；非 quick → purpose="deep"
- content 为空时回退 metadata.raw_reasoning
- agent="xxx" → trace.name + trace.metadata.agent
- max_tokens / temperature（默认 0.3）按调用方原值保留
- report.py 的 llm_config（dict 或 LLMConfig）→ 请求级 dict（复刻
  legacy._request_config_dict：cfg.apiKey → api_key 参数 → env 回退）

mock 返回 ``(text, metadata)`` 元组（与 gateway.complete_text 契约一致，
模式同 tests/evals/test_judges.py）。
"""

from unittest.mock import patch

_NLP_CT = "finance_agent.nlp.complete_text"
_REACT_CT = "finance_agent.react_agent.complete_text"
_WEB_CT = "finance_agent.events.web_fetcher.complete_text"
_REPORT_CT = "finance_agent.nodes.report.complete_text"


class TestNlpMigration:
    """nlp.py:77 intent 解析（purpose=deep, max_tokens=100, agent=intent_parser）。"""

    @patch(_NLP_CT)
    def test_resolve_with_llm_uses_purpose_deep_and_trace(self, mock_ct):
        mock_ct.return_value = (
            '{"stock_code": "600519", "stock_name": "贵州茅台", "confidence": "high"}',
            {"raw_reasoning": ""},
        )
        from finance_agent.nlp import _resolve_with_llm

        result = _resolve_with_llm("贵州茅台", api_key="sk-test")
        assert result == {"stock_code": "600519", "stock_name": "贵州茅台"}
        mock_ct.assert_called_once()
        args, kwargs = mock_ct.call_args
        # messages: system + user（与 legacy 构造一致）
        assert args[0][0]["role"] == "system"
        assert args[0][0]["content"]
        assert args[0][1]["role"] == "user"
        assert kwargs["purpose"] == "deep"
        assert kwargs["max_tokens"] == 100
        assert kwargs["temperature"] == 0.3
        assert kwargs["trace"] == {
            "name": "intent_parser",
            "metadata": {"agent": "intent_parser"},
        }
        # 无 llm_config：legacy._request_config_dict(None, api_key) 返回 None
        assert kwargs["llm_config"] is None

    @patch(_NLP_CT)
    def test_resolve_with_llm_empty_text_falls_back_to_reasoning(self, mock_ct):
        """content 为空时回退 raw_reasoning（legacy 行为）。"""
        mock_ct.return_value = (
            "",
            {
                "raw_reasoning": (
                    '{"stock_code": "300750", "stock_name": "宁德时代", "confidence": "high"}'
                )
            },
        )
        from finance_agent.nlp import _resolve_with_llm

        result = _resolve_with_llm("宁德时代")
        assert result == {"stock_code": "300750", "stock_name": "宁德时代"}

    @patch(_NLP_CT)
    def test_resolve_with_llm_low_confidence_returns_none(self, mock_ct):
        mock_ct.return_value = (
            '{"stock_code": null, "stock_name": null, "confidence": "low"}',
            {},
        )
        from finance_agent.nlp import _resolve_with_llm

        assert _resolve_with_llm("不存在的股票描述") is None


class TestReactAgentMigration:
    """react_agent.py:369/_search_with_llm_reasoning 与 432/_search_with_web_search。"""

    @patch(_REACT_CT)
    def test_search_with_llm_reasoning_uses_quick_200(self, mock_ct):
        mock_ct.return_value = (
            '{"stock_code": "600519", "stock_name": "贵州茅台", '
            '"confidence": "high", "reason": "常识映射"}',
            {},
        )
        from finance_agent.react_agent import _search_with_llm_reasoning

        result = _search_with_llm_reasoning("茅台")
        assert result == {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "confidence": "high",
            "reason": "常识映射",
        }
        _, kwargs = mock_ct.call_args
        assert kwargs["purpose"] == "quick"
        assert kwargs["max_tokens"] == 200
        assert kwargs["temperature"] == 0.3
        assert kwargs["trace"] == {"name": "react_agent", "metadata": {"agent": "react_agent"}}
        assert kwargs["llm_config"] is None

    @patch(_REACT_CT)
    def test_search_with_llm_reasoning_empty_fallback(self, mock_ct):
        """quick 档位同样复刻空文本回退。"""
        mock_ct.return_value = (
            "",
            {
                "raw_reasoning": (
                    '{"stock_code": "300308", "stock_name": "中际旭创", '
                    '"confidence": "high", "reason": "光模块龙头"}'
                )
            },
        )
        from finance_agent.react_agent import _search_with_llm_reasoning

        result = _search_with_llm_reasoning("光模块龙头")
        assert result["stock_code"] == "300308"

    @patch("finance_agent.react_agent._verify_stock_code")
    @patch("finance_agent.react_agent.format_search_for_llm")
    @patch("finance_agent.react_agent.tavily_search")
    @patch(_REACT_CT)
    def test_search_with_web_search_uses_quick_400(
        self, mock_ct, mock_tavily, mock_fmt, mock_verify
    ):
        from types import SimpleNamespace

        mock_tavily.return_value = SimpleNamespace(
            results=[{"title": "t", "url": "u", "content": "c"}]
        )
        mock_fmt.return_value = "搜索结果文本"
        mock_verify.return_value = {"stock_code": "600519", "stock_name": "贵州茅台"}
        mock_ct.return_value = (
            '{"candidates": [{"stock_code": "600519", "stock_name": "贵州茅台", '
            '"reason": "搜索结果"}]}',
            {},
        )
        from finance_agent.react_agent import _search_with_web_search

        result = _search_with_web_search("茅台")
        assert result == [{"stock_code": "600519", "stock_name": "贵州茅台"}]
        _, kwargs = mock_ct.call_args
        assert kwargs["purpose"] == "quick"
        assert kwargs["max_tokens"] == 400
        assert kwargs["temperature"] == 0.3
        assert kwargs["trace"] == {"name": "react_agent", "metadata": {"agent": "react_agent"}}


class TestWebFetcherMigration:
    """events/web_fetcher.py:135 事件提取（purpose=deep, temperature=0.1）。"""

    @patch("finance_agent.events.web_fetcher._search_with_duckduckgo")
    @patch(_WEB_CT)
    def test_fetch_events_uses_temperature_0_1(self, mock_ct, mock_search):
        mock_search.return_value = [{"source": "example.com", "title": "T", "snippet": "S"}]
        mock_ct.return_value = (
            '[{"date": "2026-01-01", "type": "提价", "title": "提价", '
            '"summary": "S", "impact": "positive", "source": "example.com", "level": "L1"}]',
            {},
        )
        from finance_agent.events.web_fetcher import fetch_events_from_web

        result = fetch_events_from_web("600519", "贵州茅台")
        assert isinstance(result, list) and len(result) == 1
        assert result[0]["type"] == "提价"
        _, kwargs = mock_ct.call_args
        assert kwargs["purpose"] == "deep"
        assert kwargs["temperature"] == 0.1
        assert "max_tokens" not in kwargs  # 无显式 → gateway capability 默认
        assert kwargs["trace"] == {"name": "web_fetcher", "metadata": {"agent": "web_fetcher"}}
        assert kwargs["llm_config"] is None

    @patch("finance_agent.events.web_fetcher._search_with_duckduckgo")
    @patch(_WEB_CT)
    def test_fetch_events_empty_text_falls_back_to_reasoning(self, mock_ct, mock_search):
        mock_search.return_value = [{"source": "example.com", "title": "T", "snippet": "S"}]
        mock_ct.return_value = (
            "",
            {
                "raw_reasoning": (
                    '[{"date": "2026-01-01", "type": "战略合作", "title": "合作", '
                    '"summary": "S", "impact": "neutral", "source": "example.com", '
                    '"level": "L2", '
                    '"summary_suffix": "【L2前瞻信号，影响周期1-2年，需跟踪后续兑现】"}]'
                )
            },
        )
        from finance_agent.events.web_fetcher import fetch_events_from_web

        result = fetch_events_from_web("600519", "贵州茅台")
        assert result and result[0]["type"] == "战略合作"


class TestReportNodeMigration:
    """nodes/report.py:144 focus 摘要（purpose=quick, max_tokens=400, llm_config 透传）。"""

    def _state_with_llm_config(self, llm_config, api_key=None):
        from finance_agent.models import AnalystReport

        return {
            "stock_name": "贵州茅台",
            "api_key": api_key,
            "analyst_reports": {
                "fundamental": AnalystReport(
                    agent_name="fundamental",
                    summary="基本面强劲",
                    key_findings=["ROE 28.33%"],
                    claims=[],
                    markdown="## 基本面分析\n...",
                ),
            },
            "llm_config": llm_config,
        }

    @patch(_REPORT_CT)
    def test_focus_summary_uses_quick_and_request_dict(self, mock_ct):
        """llm_config dict → 请求级 dict 原样透传（cfg.apiKey 优先）。"""
        mock_ct.return_value = ("围绕估值的摘要文本", {})
        from finance_agent.nodes.report import _build_focus_summary

        state = self._state_with_llm_config(
            {
                "model": "deepseek/deepseek-chat",
                "baseUrl": "https://api.test.com/v1",
                "apiKey": "sk-cfg",
            },
            api_key="sk-param",
        )
        result = _build_focus_summary(state, "估值", ["valuation"])
        assert result == "围绕估值的摘要文本"
        _, kwargs = mock_ct.call_args
        assert kwargs["purpose"] == "quick"
        assert kwargs["max_tokens"] == 400
        assert kwargs["temperature"] == 0.3
        assert kwargs["trace"] == {"name": "report", "metadata": {"agent": "report"}}
        assert kwargs["llm_config"] == {
            "model": "deepseek/deepseek-chat",
            "baseUrl": "https://api.test.com/v1",
            "apiKey": "sk-cfg",
        }

    @patch(_REPORT_CT)
    def test_focus_summary_api_key_merges_when_cfg_missing(self, mock_ct):
        """cfg.apiKey 缺省时 api_key 参数兜底（legacy._request_config_dict 回退链）。"""
        mock_ct.return_value = ("摘要", {})
        from finance_agent.nodes.report import _build_focus_summary

        state = self._state_with_llm_config(
            {"model": "deepseek/deepseek-chat", "baseUrl": "https://api.test.com/v1"},
            api_key="sk-param",
        )
        _build_focus_summary(state, "增长", ["growth"])
        _, kwargs = mock_ct.call_args
        assert kwargs["llm_config"]["apiKey"] == "sk-param"

    @patch(_REPORT_CT)
    def test_focus_summary_base_url_falls_back_to_env(self, mock_ct):
        """cfg.baseUrl 缺省时回退 env LLM_BASE_URL（legacy._request_config_dict）。"""
        from unittest.mock import patch

        mock_ct.return_value = ("摘要", {})
        from finance_agent.nodes.report import _build_focus_summary

        state = self._state_with_llm_config({"model": "deepseek/deepseek-chat"})
        with patch.dict("os.environ", {"LLM_BASE_URL": "https://env.example.com/v1"}):
            _build_focus_summary(state, "估值", ["valuation"])
        _, kwargs = mock_ct.call_args
        assert kwargs["llm_config"]["baseUrl"] == "https://env.example.com/v1"

    @patch(_REPORT_CT)
    def test_focus_summary_no_llm_config_returns_none(self, mock_ct):
        """state 无 llm_config 时 llm_config 不传（env/preset 解析，零漂移）。"""
        mock_ct.return_value = ("摘要", {})
        from finance_agent.nodes.report import _build_focus_summary

        state = self._state_with_llm_config(None)
        _build_focus_summary(state, "风险", ["risk"])
        _, kwargs = mock_ct.call_args
        assert kwargs["llm_config"] is None

    @patch(_REPORT_CT)
    def test_focus_summary_empty_text_falls_back_to_reasoning(self, mock_ct):
        mock_ct.return_value = ("", {"raw_reasoning": "来自思考链的摘要"})
        from finance_agent.nodes.report import _build_focus_summary

        state = self._state_with_llm_config(None)
        result = _build_focus_summary(state, "估值", ["valuation"])
        assert result == "来自思考链的摘要"

    @patch(_REPORT_CT)
    def test_focus_summary_empty_all_falls_back_to_analyst(self, mock_ct):
        """complete_text 与 reasoning 都为空 → 结构性兜底（取首个 summary 截断）。"""
        mock_ct.return_value = ("", {"raw_reasoning": ""})
        from finance_agent.nodes.report import _build_focus_summary

        state = self._state_with_llm_config(None)
        result = _build_focus_summary(state, "估值", ["valuation"])
        assert result == "[fundamental] 基本面强劲"
