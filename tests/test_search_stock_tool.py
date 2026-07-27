"""search_stock 工具测试。

验证 search_stock 工具正确包装 search_stock_tool 并返回格式化结果。
"""

from unittest.mock import patch

import pytest

from finance_agent.agent_factory import _make_search_stock
from finance_agent.react_agent import _classify_input, search_stock_tool


class TestSearchStockTool:
    """search_stock 工具行为测试。"""

    @pytest.mark.asyncio
    async def test_resolves_stock_name_to_code(self):
        """工具将"茅台"解析为股票代码 600519。"""
        mock_result = {
            "candidates": [{"code": "600519", "name": "贵州茅台", "market": "SH"}],
            "found": True,
            "source": "akshare_exact",
            "confidence": 1.0,
        }

        with patch("finance_agent.react_agent.search_stock_tool", return_value=mock_result):
            search_stock = _make_search_stock(api_key="test-key")
            result = await search_stock(query="茅台")

        assert "600519" in result
        assert "贵州茅台" in result

    @pytest.mark.asyncio
    async def test_not_found_returns_message(self):
        """未找到股票时返回提示信息。"""
        mock_result = {
            "candidates": [],
            "found": False,
            "message": "未找到匹配的股票",
        }

        with patch("finance_agent.react_agent.search_stock_tool", return_value=mock_result):
            search_stock = _make_search_stock(api_key="test-key")
            result = await search_stock(query="不存在的股票")

        assert "未找到" in result or "未找到匹配" in result

    @pytest.mark.asyncio
    async def test_multiple_candidates(self):
        """多候选时返回所有选项。"""
        mock_result = {
            "candidates": [
                {"code": "600519", "name": "贵州茅台", "market": "SH"},
                {"code": "000858", "name": "五粮液", "market": "SZ"},
            ],
            "found": True,
            "source": "akshare_fuzzy",
            "confidence": 0.4,
            "needs_confirmation": True,
        }

        with patch("finance_agent.react_agent.search_stock_tool", return_value=mock_result):
            search_stock = _make_search_stock(api_key="test-key")
            result = await search_stock(query="茅台")

        assert "600519" in result
        assert "贵州茅台" in result
        assert "000858" in result
        assert "五粮液" in result

    @pytest.mark.asyncio
    async def test_api_key_passed_through(self):
        """api_key 通过闭包正确传递给 search_stock_tool。"""
        with patch("finance_agent.react_agent.search_stock_tool") as mock_func:
            mock_func.return_value = {"candidates": [], "found": False, "message": "test"}
            search_stock = _make_search_stock(api_key="my-secret-key")
            await search_stock(query="茅台")

            mock_func.assert_called_once_with("茅台", "my-secret-key")


class TestClassifyInput:
    """_classify_input 输入分类（零 LLM）。"""

    def test_hot_stocks_phrase_is_description(self):
        assert _classify_input("分析一下热门股票") == "description"

    def test_hot_keyword_is_description(self):
        assert _classify_input("热门股票") == "description"

    def test_recommend_short_is_description(self):
        assert _classify_input("推荐股") == "description"

    def test_pure_name_still_name(self):
        assert _classify_input("贵州茅台") == "name"

    def test_concept_still_description(self):
        assert _classify_input("白酒龙头") == "description"

    def test_code_still_code(self):
        assert _classify_input("600519") == "code"


class TestSearchStockTimeSensitiveGuard:
    """时效性查询（热门/推荐/今天…）不应走 LLM 常识推理，避免幻觉出单只股票。"""

    def test_hot_stocks_skips_llm_reasoning(self):
        """即使 LLM 会幻觉出贵州茅台，时效性守卫也不应让它通过。"""
        hallucinated = {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "confidence": "high",
        }
        with (
            patch("finance_agent.react_agent._search_with_llm_reasoning") as mock_llm,
            patch("finance_agent.react_agent.has_tavily_key", return_value=False),
            patch("finance_agent.react_agent._akshare_fuzzy_search", return_value=[]),
        ):
            mock_llm.return_value = hallucinated
            result = search_stock_tool("分析一下热门股票")

        mock_llm.assert_not_called()
        assert not (len(result.get("candidates", [])) == 1 and result.get("confidence", 0) >= 0.9)

    def test_hot_stocks_uses_web_search_when_available(self):
        web_candidates = [
            {"stock_code": "600519", "stock_name": "贵州茅台"},
            {"stock_code": "300750", "stock_name": "宁德时代"},
        ]
        with (
            patch("finance_agent.react_agent._search_with_llm_reasoning") as mock_llm,
            patch("finance_agent.react_agent.has_tavily_key", return_value=True),
            patch("finance_agent.react_agent._search_with_web_search") as mock_web,
            patch("finance_agent.react_agent._akshare_fuzzy_search") as mock_fuzzy,
        ):
            mock_llm.return_value = {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "confidence": "high",
            }
            mock_web.return_value = web_candidates
            result = search_stock_tool("热门股票")

        mock_llm.assert_not_called()
        mock_web.assert_called_once()
        mock_fuzzy.assert_not_called()
        assert result.get("needs_confirmation") is True
        assert len(result["candidates"]) == 2

    def test_concept_query_still_uses_llm_reasoning(self):
        """概念词（如"龙头"）仍走 LLM 推理，这是稳定的常识映射，不应被守卫拦截。"""
        verified = {"stock_code": "600519", "stock_name": "贵州茅台"}
        with (
            patch("finance_agent.react_agent._search_with_llm_reasoning") as mock_llm,
            patch("finance_agent.react_agent._verify_stock_code", return_value=verified),
        ):
            mock_llm.return_value = {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "confidence": "high",
            }
            result = search_stock_tool("白酒龙头")

        mock_llm.assert_called_once()
        assert result.get("found") is True
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["stock_code"] == "600519"
