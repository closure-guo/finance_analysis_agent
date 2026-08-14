"""工具调用嵌套 arguments 解包测试。

背景（已确诊）：模型（Console Go relay）调用工具时 arguments 偶发返回嵌套格式
`{"arguments": "{...}"}` 而非直接参数。`_parse_tool_calls` 只做 json.loads 不解包
→ `func(**{"arguments": ...})` → `run_deep_analysis(arguments=...)` TypeError
→ 工具失败 → 重试级联 → 重试轮缺 reasoning_content → DeepSeek 400。

修复：新增模块级 helper `_normalize_tool_args`，在 `_parse_tool_calls` 的
`json.loads(...)` 后应用，将嵌套格式解包为真正参数。

对应 change: fix/tool-args-nesting（bug 修复，意图不变，不立新 delta）。
"""

from __future__ import annotations

from finance_agent.harness.litellm_client import LiteLLMClient, _normalize_tool_args

# ── 单元测试：_normalize_tool_args ──


def test_normalize_unwraps_string_json():
    """嵌套 str JSON：{"arguments": '{"stock_code": "300308"}'} → 真正参数 dict。"""
    result = _normalize_tool_args({"arguments": '{"stock_code": "300308"}'})
    assert result == {"stock_code": "300308"}


def test_normalize_unwraps_nested_dict():
    """嵌套 dict：{"arguments": {"stock_code": "300308"}} → 直接解包。"""
    result = _normalize_tool_args({"arguments": {"stock_code": "300308"}})
    assert result == {"stock_code": "300308"}


def test_normalize_keeps_direct_args():
    """正常格式（非嵌套）SHALL 原样返回，行为不变。"""
    args = {"stock_code": "300308"}
    assert _normalize_tool_args(args) is args


def test_normalize_keeps_empty_dict():
    """空 dict 原样返回。"""
    assert _normalize_tool_args({}) == {}


def test_normalize_keeps_multiple_keys():
    """多键 dict（非单一 arguments 键）原样返回。"""
    args = {"a": 1, "b": 2}
    assert _normalize_tool_args(args) is args


def test_normalize_keeps_invalid_inner_json():
    """嵌套但 inner 非合法 JSON 字符串时 SHALL 原样返回（降级不抛错）。"""
    args = {"arguments": "not-valid-json"}
    assert _normalize_tool_args(args) is args


def test_normalize_keeps_non_arguments_scalar():
    """单一键但值非 str/dict（如 int）时原样返回。"""
    args = {"arguments": 42}
    assert _normalize_tool_args(args) is args


# ── 集成测试：_parse_tool_calls 端到端解包 ──


def test_parse_tool_calls_unwraps_nested_arguments():
    """_parse_tool_calls 收到嵌套 arguments SHALL 返回解包后的 ToolCallRequest.arguments。

    直接构造 raw_calls dict 调 _parse_tool_calls，无需网络/LLM。
    """
    client = LiteLLMClient(model="deepseek-chat", api_key="fake")
    raw_calls = {
        0: {
            "id": "call_0",
            "function": {
                "name": "run_deep_analysis",
                # 模型偶发返回嵌套格式：外层 arguments 的 JSON 字符串内再包一层 arguments
                "arguments": '{"arguments": "{\\"stock_code\\": \\"300308\\"}"}',
            },
        }
    }

    results = client._parse_tool_calls(raw_calls)

    assert len(results) == 1
    assert results[0].name == "run_deep_analysis"
    assert results[0].arguments == {"stock_code": "300308"}


def test_parse_tool_calls_keeps_normal_arguments():
    """正常格式 arguments SHALL 保持解包行为不变（回归保护）。"""
    client = LiteLLMClient(model="deepseek-chat", api_key="fake")
    raw_calls = {
        0: {
            "id": "call_0",
            "function": {
                "name": "run_deep_analysis",
                "arguments": '{"stock_code": "300308"}',
            },
        }
    }

    results = client._parse_tool_calls(raw_calls)

    assert results[0].arguments == {"stock_code": "300308"}
