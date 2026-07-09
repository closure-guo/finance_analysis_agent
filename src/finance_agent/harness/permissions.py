"""
Mini Harness - Permission System
权限系统：Deny-first 规则引擎 + 渐进信任策略

设计原则（来自 Claude Code）：
1. Deny > Ask > Allow：最严格的规则获胜
2. 人类审批会退化（93% 的权限请求被惯性点击批准）
3. 安全必须是基础设施层面的自动机制，不能依赖人类持续警惕
4. 权限模式构成从完全手动到完全自动的光谱
"""

from __future__ import annotations

import fnmatch
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from finance_agent.harness.types import PermissionMode, PermissionRequest, RiskLevel

logger = logging.getLogger("finance_agent.harness.permissions")


# ───────────────────────────────────────────────
# Deny-first 规则引擎
# ───────────────────────────────────────────────


@dataclass
class DenyRule:
    """
    拒绝规则 -- 匹配即拒绝，无需询问。
    这是 Deny-first 安全姿态的核心。
    """

    tool_name: str | None = None  # None = 匹配所有工具
    path_pattern: str | None = None  # 文件路径 glob 模式
    command_pattern: str | None = None  # 命令 regex/glob
    reason: str = "匹配拒绝规则"

    def matches(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """检查工具调用是否匹配此规则"""
        if self.tool_name and self.tool_name != tool_name:
            return False
        if self.path_pattern:
            path = arguments.get("path", arguments.get("file_path", ""))
            if not fnmatch.fnmatch(str(path), self.path_pattern):
                return False
        if self.command_pattern:
            cmd = arguments.get("command", "")
            if not fnmatch.fnmatch(str(cmd), self.command_pattern):
                return False
        return True


# ───────────────────────────────────────────────
# 权限决策器基类
# ───────────────────────────────────────────────


class PermissionChecker:
    """
    权限检查器 -- 决定操作是否被允许。

    架构：
    - 规则引擎（Deny-first）
    - 模式策略（根据 PermissionMode 采用不同策略）
    - 可自定义回调（用于交互式确认）
    """

    # 内置风险等级映射
    DEFAULT_RISK_MAP: dict[str, RiskLevel] = {
        # 文件操作
        "read_file": RiskLevel.READ,
        "write_file": RiskLevel.HIGH,
        "edit_file": RiskLevel.MEDIUM,
        "delete_file": RiskLevel.CRITICAL,
        "list_directory": RiskLevel.READ,
        # 命令执行
        "run_command": RiskLevel.HIGH,
        "run_shell": RiskLevel.CRITICAL,
        # 网络
        "web_search": RiskLevel.MEDIUM,
        "fetch_url": RiskLevel.HIGH,
        "http_request": RiskLevel.CRITICAL,
        # 代码
        "run_python": RiskLevel.HIGH,
        "run_test": RiskLevel.LOW,
    }

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.NORMAL,
        deny_rules: list[DenyRule] | None = None,
        risk_map: dict[str, RiskLevel] | None = None,
        interactive_callback: Callable[[PermissionRequest], Coroutine[Any, Any, bool]]
        | None = None,
    ):
        self.mode = mode
        self.deny_rules: list[DenyRule] = deny_rules or self._default_deny_rules()
        self.risk_map = {**self.DEFAULT_RISK_MAP, **(risk_map or {})}
        self.interactive_callback = interactive_callback
        # 统计
        self.stats: dict[str, int] = {"allowed": 0, "denied": 0, "asked": 0}

    # ── 核心决策入口 ──

    async def check(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """
        权限检查主入口。
        返回 True = 允许执行，False = 拒绝。

        决策流程：
        1. Deny-first 规则检查 -> 匹配则直接拒绝
        2. 根据 PermissionMode 决定策略
        3. 如需要，调用交互式确认
        """
        # 1. Deny-first 规则
        for rule in self.deny_rules:
            if rule.matches(tool_name, arguments):
                logger.warning(f"[DENY] {tool_name} 匹配拒绝规则: {rule.reason}")
                self.stats["denied"] += 1
                return False

        # 2. 根据模式决策
        risk = self._assess_risk(tool_name, arguments)
        decision = await self._decide_by_mode(tool_name, arguments, risk)

        if decision:
            self.stats["allowed"] += 1
        else:
            self.stats["denied"] += 1
        return decision

    # ── 模式策略 ──

    async def _decide_by_mode(
        self, tool_name: str, arguments: dict[str, Any], risk: RiskLevel
    ) -> bool:
        """根据当前权限模式做出决策"""

        if self.mode == PermissionMode.YOLO:
            # YOLO 模式：全部允许
            return True

        if self.mode == PermissionMode.ASK:
            # Ask 模式：所有操作都需确认
            return await self._ask(
                PermissionRequest(
                    tool_name=tool_name,
                    arguments=arguments,
                    risk_level=risk,
                    reason="Ask 模式下所有操作都需确认",
                )
            )

        if risk == RiskLevel.READ:
            # 读操作在 NORMAL 和 AUTO 模式下自动允许
            return True

        if self.mode == PermissionMode.NORMAL:
            # NORMAL：写操作需确认，读操作自动
            if risk in (RiskLevel.LOW, RiskLevel.READ):
                return True
            return await self._ask(
                PermissionRequest(
                    tool_name=tool_name,
                    arguments=arguments,
                    risk_level=risk,
                    reason="NORMAL 模式下写操作需确认",
                )
            )

        if self.mode == PermissionMode.AUTO_EDIT:
            # AUTO_EDIT：文件编辑自动，其他写操作需确认
            if tool_name in ("write_file", "edit_file"):
                return True
            if risk in (RiskLevel.LOW, RiskLevel.READ):
                return True
            return await self._ask(
                PermissionRequest(
                    tool_name=tool_name,
                    arguments=arguments,
                    risk_level=risk,
                    reason="AUTO_EDIT 模式下非编辑写操作需确认",
                )
            )

        if self.mode == PermissionMode.AUTO:
            # AUTO：AI 判断 -- 简化实现：低风险自动，高风险询问
            if risk in (RiskLevel.READ, RiskLevel.LOW):
                return True
            if risk == RiskLevel.MEDIUM:
                # 可以扩展为 ML 分类器判断
                return True
            return await self._ask(
                PermissionRequest(
                    tool_name=tool_name,
                    arguments=arguments,
                    risk_level=risk,
                    reason="AUTO 模式下高风险操作需确认",
                )
            )

        return True

    async def _ask(self, request: PermissionRequest) -> bool:
        """交互式确认"""
        self.stats["asked"] += 1
        if self.interactive_callback:
            return await self.interactive_callback(request)
        # 无回调时的默认行为：拒绝（安全默认）
        logger.warning(f"[ASK -> DENY] 无交互回调，默认拒绝: {request.describe()}")
        return False

    # ── 风险评估 ──

    def _assess_risk(self, tool_name: str, arguments: dict[str, Any]) -> RiskLevel:
        """评估操作风险等级"""
        base_risk = self.risk_map.get(tool_name, RiskLevel.MEDIUM)

        # 基于参数提升风险
        cmd = str(arguments.get("command", ""))
        if "rm -rf" in cmd or "del /f" in cmd:
            return RiskLevel.CRITICAL
        if "sudo" in cmd or "chmod 777" in cmd:
            return RiskLevel.CRITICAL
        if "curl" in cmd and "| sh" in cmd:
            return RiskLevel.CRITICAL

        path = str(arguments.get("path", ""))
        sensitive_paths = [".env", ".ssh/", ".aws/", "/etc/passwd", "id_rsa"]
        for sp in sensitive_paths:
            if sp in path:
                return RiskLevel.CRITICAL

        return base_risk

    # ── 规则管理 ──

    def add_deny_rule(self, rule: DenyRule) -> None:
        """添加拒绝规则"""
        self.deny_rules.append(rule)

    def remove_deny_rule(self, tool_name: str, path_pattern: str | None = None) -> None:
        """移除拒绝规则"""
        self.deny_rules = [
            r
            for r in self.deny_rules
            if not (r.tool_name == tool_name and r.path_pattern == path_pattern)
        ]

    @staticmethod
    def _default_deny_rules() -> list[DenyRule]:
        """默认拒绝规则 -- 保护敏感文件和危险操作"""
        return [
            DenyRule(tool_name="delete_file", path_pattern="*", reason="删除文件需显式确认"),
            DenyRule(
                tool_name="run_shell",
                command_pattern="*rm -rf /*",
                reason="危险命令：删除整个文件系统",
            ),
            DenyRule(tool_name="run_shell", command_pattern="*sudo*", reason="危险命令：提权操作"),
            DenyRule(tool_name="write_file", path_pattern="*.pem", reason="敏感文件：证书"),
            DenyRule(tool_name="write_file", path_pattern=".ssh/*", reason="敏感目录：SSH 密钥"),
            DenyRule(tool_name="write_file", path_pattern=".env*", reason="敏感文件：环境变量"),
            DenyRule(tool_name="http_request", command_pattern="*", reason="网络请求需显式确认"),
        ]

    def __repr__(self) -> str:
        return f"PermissionChecker(mode={self.mode.value}, allowed={self.stats['allowed']}, denied={self.stats['denied']})"
