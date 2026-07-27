"""
Mini Harness - Hooks System
生命周期钩子：事件驱动的扩展机制

设计原则（来自 Claude Code 的 27 种 Hook 类型）：
- Hooks 是 Agent 事件的确定性反应，不是模型推理
- 允许外部系统在特定生命周期点插入自定义逻辑
- 预定义挂载点，类型安全
- 支持异步回调

使用场景：
- 工具调用前：记录审计日志、阻止危险操作
- 工具调用后：自动运行测试、发送通知
- 会话开始：加载项目配置
- 会话结束：生成摘要
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from finance_agent.harness.types import HookPoint

logger = logging.getLogger("finance_agent.harness.hooks")

# 钩子回调类型
HookCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class HookManager:
    """
    钩子管理器 -- 事件订阅与分发

    类比：类似于 Node.js 的 EventEmitter，但挂载点是预定义的枚举。
    """

    def __init__(self):
        # 每个挂载点对应一个回调列表
        self._subscribers: dict[HookPoint, list[HookCallback]] = {point: [] for point in HookPoint}

    # ── 订阅 ──

    def on(self, point: HookPoint, callback: HookCallback) -> None:
        """订阅指定挂载点的事件"""
        self._subscribers[point].append(callback)
        logger.debug(f"钩子订阅: {point.value} -> {callback.__name__}")

    def once(self, point: HookPoint, callback: HookCallback) -> None:
        """订阅一次，触发后自动取消"""

        async def wrapper(context: dict[str, Any]) -> None:
            await callback(context)
            self.off(point, wrapper)

        wrapper.__name__ = f"once_{callback.__name__}"
        self.on(point, wrapper)

    def off(self, point: HookPoint, callback: HookCallback) -> None:
        """取消订阅"""
        if callback in self._subscribers[point]:
            self._subscribers[point].remove(callback)

    # ── 分发 ──

    async def emit(self, point: HookPoint, context: dict[str, Any]) -> None:
        """触发指定挂载点的所有回调"""
        callbacks = self._subscribers.get(point, [])
        if not callbacks:
            return

        for callback in callbacks:
            try:
                await callback(context)
            except Exception as e:
                logger.warning(f"钩子执行失败 [{point.value}]: {e}")
                # 钩子失败不应中断主流程

    # ── 便捷方法 ──

    def pre_tool_use(self, callback: HookCallback) -> None:
        """工具调用前的快捷订阅"""
        self.on(HookPoint.PRE_TOOL_USE, callback)

    def post_tool_use(self, callback: HookCallback) -> None:
        """工具调用后的快捷订阅"""
        self.on(HookPoint.POST_TOOL_USE, callback)

    def on_session_start(self, callback: HookCallback) -> None:
        """会话开始的快捷订阅"""
        self.on(HookPoint.ON_SESSION_START, callback)

    def on_session_end(self, callback: HookCallback) -> None:
        """会话结束的快捷订阅"""
        self.on(HookPoint.ON_SESSION_END, callback)

    def on_error(self, callback: HookCallback) -> None:
        """错误事件的快捷订阅"""
        self.on(HookPoint.ON_ERROR, callback)

    def __repr__(self) -> str:
        total = sum(len(v) for v in self._subscribers.values())
        return f"HookManager({total} hooks across {len(self._subscribers)} points)"


# ───────────────────────────────────────────────
# 常用 Hook 工厂函数
# ───────────────────────────────────────────────


def audit_log_hook(log_file: str = "agent_audit.log") -> HookCallback:
    """
    审计日志 Hook -- 记录所有工具调用

    用法：
        hooks.pre_tool_use(audit_log_hook("audit.log"))
    """

    async def callback(context: dict[str, Any]) -> None:
        import json
        from datetime import datetime

        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": context.get("tool_name", "unknown"),
            "args": context.get("arguments", {}),
            "session_id": context.get("session_id", "default"),
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return callback


def auto_test_hook(test_command: str = "pytest") -> HookCallback:
    """
    自动测试 Hook -- 文件编辑后自动运行测试

    用法：
        hooks.post_tool_use(auto_test_hook("pytest -x"))
    """

    async def callback(context: dict[str, Any]) -> None:
        tool_name = context.get("tool_name", "")
        if tool_name not in ("write_file", "edit_file"):
            return

        import subprocess

        try:
            result = subprocess.run(  # noqa: S603 - test_command 来自配置，非用户输入
                test_command.split(), capture_output=True, text=True, timeout=60
            )
            logger.info(f"自动测试: exit={result.returncode}")
        except Exception as e:
            logger.warning(f"自动测试失败: {e}")

    return callback


def rate_limit_hook(max_calls: int = 30, window_seconds: int = 60) -> HookCallback:
    """
    速率限制 Hook -- 限制工具调用频率

    用法：
        hooks.pre_tool_use(rate_limit_hook(max_calls=50))
    """
    import time
    from collections import deque

    call_times: deque = deque()

    async def callback(context: dict[str, Any]) -> None:
        now = time.time()
        # 清理过期记录
        while call_times and call_times[0] < now - window_seconds:
            call_times.popleft()

        if len(call_times) >= max_calls:
            raise RuntimeError(f"速率限制: 每 {window_seconds} 秒最多 {max_calls} 次工具调用")

        call_times.append(now)

    return callback
