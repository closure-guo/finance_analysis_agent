"""langfuse_tracing.open_span 单元测试。

验证 open_span 在三种场景下的行为：
1. Langfuse 已配置时创建 span
2. Langfuse 未配置时优雅降级返回 None
3. span 创建异常时降级不影响业务
"""

import logging
from unittest.mock import MagicMock, patch

from finance_agent.langfuse_tracing import (
    get_callback_handler,
    open_span,
    truncate_for_trace,
    update_current_span,
)

# 本仓库未安装完整 langchain 包（只有 langchain-core）；langfuse.langchain 的
# CallbackHandler 强依赖完整版。该场景在每次 graph.invoke / api 请求都会触发，
# 若不静默降级会疯狂刷 traceback 噪音。
_LANGCHAIN_MISSING_MSG = "No module named 'langchain'"


def _langchain_missing_importer(name, globals=None, locals=None, fromlist=(), level=0):
    """模拟 from langfuse.langchain import CallbackHandler 因缺 langchain 抛错。"""
    if name == "langfuse.langchain":
        raise ModuleNotFoundError(_LANGCHAIN_MISSING_MSG)
    return _real_import(name, globals, locals, fromlist, level)


_real_import = __import__


class TestOpenSpan:
    """open_span 优雅降级测试。"""

    def test_langfuse_configured_creates_span(self):
        """Langfuse 已配置时调用 start_as_current_observation 创建 span。"""
        mockClient = MagicMock()
        mockCm = MagicMock()
        mockObs = MagicMock()
        mockClient.start_as_current_observation.return_value = mockCm
        mockCm.__enter__.return_value = mockObs

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            open_span("tool:web_search", {"args": {"query": "test"}}) as obs,
        ):
            # 在 span 上下文内，obs 是 observation 对象
            assert obs is mockObs

        # 验证 start_as_current_observation 被正确调用
        mockClient.start_as_current_observation.assert_called_once_with(
            name="tool:web_search", as_type="span", input={"args": {"query": "test"}}
        )
        # 验证 span 上下文正确退出
        mockCm.__exit__.assert_called_once()

    def test_langfuse_not_configured_returns_none(self):
        """Langfuse 未配置时返回 None，不抛异常、不创建 span。"""
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
            open_span("tool:web_search", {"args": {}}) as obs,
        ):
            assert obs is None

    def test_span_creation_exception_degrades(self):
        """start_as_current_observation 抛异常时降级为 None，业务流程继续。"""
        mockClient = MagicMock()
        mockClient.start_as_current_observation.side_effect = RuntimeError("langfuse down")

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            open_span("tool:web_search", {"args": {}}) as obs,
        ):
            # 降级后 obs 为 None，但业务代码仍能继续执行
            assert obs is None

    def test_open_span_allows_output_update(self):
        """调用方可在 span 内用 obs.update 记录 output。"""
        mockClient = MagicMock()
        mockObs = MagicMock()
        mockClient.start_as_current_observation.return_value = MagicMock()
        mockClient.start_as_current_observation.return_value.__enter__.return_value = mockObs

        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            open_span("tool:echo", {"args": {"text": "hi"}}) as obs,
        ):
            if obs:
                obs.update(output={"result": "echo: hi"})

        mockObs.update.assert_called_once_with(output={"result": "echo: hi"})


def test_update_current_span_noop_when_unconfigured():
    """未配置 Langfuse 时 update_current_span 不报错（降级）。"""
    with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None):
        # 不应抛异常
        update_current_span(metadata={"x": 1}, level="WARNING")


def test_update_current_span_calls_client():
    """已配置时透传 metadata + level 到 client.update_current_span。"""
    mockClient = MagicMock()
    with patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient):
        update_current_span(metadata={"degradation": "parse_degraded"}, level="WARNING")
    mockClient.update_current_span.assert_called_once_with(
        metadata={"degradation": "parse_degraded"}, level="WARNING"
    )


def test_update_current_span_swallows_exception(caplog):
    """client 抛异常时不冒泡（降级），且必须留 WARNING 级日志（锁定非静默契约）。"""
    mockClient = MagicMock()
    mockClient.update_current_span.side_effect = RuntimeError("boom")
    with (
        patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
        caplog.at_level(logging.WARNING, logger="finance_agent.langfuse"),
    ):
        update_current_span(metadata={"x": 1})  # 不抛
    # 锁定降级"带日志"契约：防止未来静默删掉 warning 日志行（可观测性 helper 自身丢堆栈=反讽）
    assert any(
        "update_current_span" in rec.message and rec.levelno == logging.WARNING
        for rec in caplog.records
    ), (
        f"expected WARNING log mentioning update_current_span, got: {[r.message for r in caplog.records]}"
    )


def test_truncate_for_trace_keeps_head_tail():
    """超长文本保留首尾 + 中部省略标记；短文本原样返回。"""
    short = "abc"
    assert truncate_for_trace(short) == "abc"
    long = "X" * 20000
    out = truncate_for_trace(long, max_bytes=8192)
    assert out.startswith("X") and out.endswith("X")
    assert "[truncated" in out
    assert len(out.encode("utf-8")) <= 8192 + 200  # 标记本身占少量


def test_truncate_for_trace_handles_cjk():
    """CJK 文本 3 字节/字符必走字节边界（A 股 reasoning 中文常见场景）。

    与 ASCII 不同，UTF-8 切片点几乎必然落在多字节序列中间；errors="ignore"
    必须把孤儿字节丢弃而非拼出乱码。锁定：
    1. 函数不抛
    2. 输出可 UTF-8 roundtrip decode（无残留孤儿字节序列）
    3. 总字节数受控
    4. 首尾仍是合法"股"字符（非残字节）
    """
    text = "股" * 20000  # 60000 字节 UTF-8，远超 8192 上限
    out = truncate_for_trace(text, max_bytes=8192)
    # 输出必须可 UTF-8 decode（errors="ignore" 后无孤儿字节序列）
    out.encode("utf-8").decode("utf-8")
    # 总字节数受控（标记本身占少量）
    assert len(out.encode("utf-8")) <= 8192 + 200
    # head/tail 切片在字节边界上仍能完整 decode 成"股"
    assert out.startswith("股") and out.endswith("股")
    assert "[truncated" in out


class TestGetCallbackHandler:
    """get_callback_handler 缺 langchain 可选依赖的降级契约。

    本仓库未安装完整 langchain 包（仅 langchain-core）；langfuse.langchain 的
    CallbackHandler 强依赖完整版，import 时抛 ModuleNotFoundError。该调用在每次
    graph.invoke（evals deep 项）与 API 请求都会触发，若每次都打完整 traceback
    会刷爆日志——降级必须静默（可 debug 记录，不得 WARNING 级 exc_info 刷屏）。
    """

    def test_langchain_missing_degrades_silently(self, caplog):
        """langchain 缺失时返回 None 且不打 WARNING 级日志（静默降级）。"""
        mockClient = MagicMock()
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            patch(
                "builtins.__import__",
                side_effect=lambda *a, **k: (
                    _langchain_missing_importer(*a, **k)
                    if a and a[0] == "langfuse.langchain"
                    else _real_import(*a, **k)
                ),
            ),
            caplog.at_level(logging.WARNING, logger="finance_agent.langfuse"),
        ):
            handler = get_callback_handler()

        assert handler is None
        warn_recs = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not warn_recs, (
            f"langchain 缺失不应刷 WARNING 级 traceback, got: {[r.getMessage() for r in warn_recs]}"
        )

    def test_langchain_missing_records_debug_once(self, caplog):
        """langchain 缺失时仍可留一条 DEBUG 记录（非全静默，便于诊断）。"""
        mockClient = MagicMock()
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=mockClient),
            patch(
                "builtins.__import__",
                side_effect=lambda *a, **k: (
                    _langchain_missing_importer(*a, **k)
                    if a and a[0] == "langfuse.langchain"
                    else _real_import(*a, **k)
                ),
            ),
            caplog.at_level(logging.DEBUG, logger="finance_agent.langfuse"),
        ):
            get_callback_handler()

        debug_recs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert debug_recs, "langchain 缺失时应留 DEBUG 级诊断记录"

    def test_langfuse_unconfigured_returns_none_quiet(self, caplog):
        """langfuse 未配置时直接返回 None，无任何日志。"""
        with (
            patch("finance_agent.langfuse_tracing.get_langfuse", return_value=None),
            caplog.at_level(logging.DEBUG, logger="finance_agent.langfuse"),
        ):
            handler = get_callback_handler()
        assert handler is None
        assert not caplog.records
