"""后端 agentTimeline 构建器 —— 逐行镜像 frontend/src/timeline.ts 的 applyChatStreamEvent。

设计见 openspec/changes/persist-full-session-timeline/design.md（D2）：
后端在流式消费 SSE 事件时构建与前端同构的结构化时序，持久化到 chat_history
的 agentTimeline 字段。所有函数均为纯函数（不可变更新，返回新 list），
元素为 TimelineItem 同构 dict：

- thinking:  {"type": "thinking", "content": str, "done": bool, "title"?: str | None}
- search:    {"type": "search", "query": str, "status": "searching"|"done"|"error", "results"?: list}
- tool_call: {"type": "tool_call", "name": str, "args": str, "result"?: str, "done": bool}
"""

# 项目规范要求变量命名使用 camelCase，与 pep8-naming 的 snake_case 冲突，模块级豁免
# ruff: noqa: N806

from __future__ import annotations

import json
import re
from typing import Any

# 搜索类工具集合（与前端 SEARCH_TOOL_NAMES 保持一致；web_search / batch_web_search
# 走 search item，不进 tool_call item —— design.md 决策 8）
SEARCH_TOOL_NAMES = {"web_search", "batch_web_search"}

# 提取思考标题的正则（与前端 /^\s*##\s+(.+?)\s*$/m 等价）
_THINKING_TITLE_RE = re.compile(r"^\s*##\s+(.+?)\s*$", re.MULTILINE)


def append_thinking_token(timeline: list[dict], token: str) -> list[dict]:
    """向 timeline 追加/累加一个 thinking token：末尾是 thinking item 则累加，否则新建。

    镜像前端 appendThinkingToken：只判断末尾 type === 'thinking'，不看 done。
    """
    last = timeline[-1] if timeline else None
    if last and last.get("type") == "thinking":
        nextTimeline = list(timeline)
        nextTimeline[-1] = {**last, "content": last["content"] + token}
        return nextTimeline
    return [*timeline, {"type": "thinking", "content": token, "done": False}]


def close_last_thinking(timeline: list[dict]) -> list[dict]:
    """将末尾未完成（done 不为 True）的 thinking item 置为完成态；否则原样返回。

    镜像前端 closeLastThinking（无变化时返回同引用）。
    """
    last = timeline[-1] if timeline else None
    if last and last.get("type") == "thinking" and last.get("done") is not True:
        nextTimeline = list(timeline)
        nextTimeline[-1] = {**last, "done": True}
        return nextTimeline
    return timeline


def close_all_thinking(timeline: list[dict]) -> list[dict]:
    """将所有未完成 thinking item 置为完成态（chat_done / error 收口用）。"""
    return [
        {**item, "done": True}
        if item.get("type") == "thinking" and item.get("done") is not True
        else item
        for item in timeline
    ]


def extract_thinking_title(content: str) -> str | None:
    """从思考内容中提取首个 ## 二级标题作为横幅标题（与前端 extractThinkingTitleLocal 同策略）。"""
    if not content:
        return None
    match = _THINKING_TITLE_RE.search(content)
    return match.group(1) if match else None


def _json_dumps(value: Any) -> str:
    """JSON 序列化（ensure_ascii=False，与前端 JSON.stringify 的 UTF-16 长度语义对齐）。"""
    return json.dumps(value, ensure_ascii=False)


def summarize_tool_result(result: Any) -> str:
    """将工具结果浓缩为简短文本（与前端 summarizeToolResultLocal 同策略）。

    - str 取前 150 字符
    - list 取前 3 项的 title/name/code，或该项 JSON 前 50 字符，用「、」连接
    - dict 转 JSON 取前 150 字符
    - 其他类型返回 ''
    """
    if isinstance(result, str):
        return result[:150]
    if isinstance(result, list):
        items: list[str] = []
        for entry in result[:3]:
            # 前端 (r as Record)?.title 对非对象返回 undefined，走 JSON.stringify 分支
            if isinstance(entry, dict):
                value = entry.get("title") or entry.get("name") or entry.get("code")
                if value:
                    items.append(str(value))
                    continue
            items.append(_json_dumps(entry)[:50])
        return "、".join(items)
    if isinstance(result, dict):
        return _json_dumps(result)[:150]
    return ""


def summarize_tool_args(args: dict | None) -> str:
    """将工具调用参数浓缩为展示文本（query / queries 优先，其余非空 dict 转 JSON）。

    镜像前端 summarizeToolArgs。
    """
    if not args:
        return ""
    query = args.get("query")
    if isinstance(query, str):
        return query
    queries = args.get("queries")
    if isinstance(queries, list):
        return "、".join(str(q) for q in queries)
    return _json_dumps(args) if args else ""


# ── 管线分组件（nodeTimelines，镜像 applyPipelineThinkingToken / applyPipelineNodeComplete）──


def apply_pipeline_thinking_token(
    node_timelines: dict[str, list[dict]], node: str | None, token: str
) -> dict[str, list[dict]]:
    """管线模式：thinking_token 按 node 写入对应节点的 timeline（不可变更新）。

    镜像前端 applyPipelineThinkingToken：
    - node 缺失/空串归入 '' 键（与历史未分组思考兼容）
    - 其他节点末尾未完成的 thinking item 防御性收口（close_last_thinking）
    - 当前节点 append_thinking_token
    """
    nodeKey = node or ""
    nextTimelines: dict[str, list[dict]] = {}
    # 防御性收口：其他节点末尾未完成的 thinking item 置为完成态
    for key, timeline in node_timelines.items():
        nextTimelines[key] = timeline if key == nodeKey else close_last_thinking(timeline)
    current = nextTimelines.get(nodeKey, [])
    nextTimelines[nodeKey] = append_thinking_token(current, token)
    return nextTimelines


def apply_pipeline_node_complete(
    node_timelines: dict[str, list[dict]], node: str
) -> dict[str, list[dict]]:
    """管线模式：node_complete 将该节点末尾未完成的 thinking item 显式收口。

    镜像前端 applyPipelineNodeComplete：无该节点则原样返回同引用。
    """
    if node not in node_timelines:
        return node_timelines
    nextTimelines = dict(node_timelines)
    nextTimelines[node] = close_last_thinking(nextTimelines[node])
    return nextTimelines


def apply_pipeline_search_event(
    node_timelines: dict[str, list[dict]], node: str | None, event: dict
) -> dict[str, list[dict]]:
    """管线模式：search_start/search_result/search_error 归属当前运行节点的 timeline。

    事件本身不带 node 字段，由调用方解析「当前运行节点」传入；
    node 缺失/空串归入 '' 键（与 thinking_token 的历史未分组兼容）。
    三态语义复用 apply_chat_event（search_start append searching；
    search_result 更新最近 searching→done+results；search_error→error）。
    """
    nodeKey = node or ""
    nextTimelines = dict(node_timelines)
    nextTimelines[nodeKey] = apply_chat_event(nextTimelines.get(nodeKey, []), event)
    return nextTimelines


def apply_pipeline_tool_event(
    node_timelines: dict[str, list[dict]], node: str | None, event: dict
) -> dict[str, list[dict]]:
    """管线模式：tool_call/tool_result 归属当前运行节点的 timeline。

    语义复用 apply_chat_event（搜索类工具名跳过 tool_call item，由 search 事件承载；
    tool_call 收口末段 thinking 后 append；tool_result 同名回填/回退/仅结果项）。
    node 缺失/空串归入 '' 键。
    """
    nodeKey = node or ""
    nextTimelines = dict(node_timelines)
    nextTimelines[nodeKey] = apply_chat_event(nextTimelines.get(nodeKey, []), event)
    return nextTimelines


def apply_chat_event(timeline: list[dict], event: dict) -> list[dict]:
    """将对话流 SSE 事件应用到 agentTimeline，返回新 list（不可变更新）。

    镜像前端 applyChatStreamEvent 的 timeline 部分；chatResponse / streaming
    等消息级字段不在本函数职责内（由调用方处理）。未知事件原样返回同引用。
    """
    eventType = event.get("type")

    if eventType == "thinking_token":
        return append_thinking_token(timeline, event.get("token", ""))

    if eventType == "thinking_replace":
        # DSML 清理等后处理：整体替换末尾 thinking item 内容
        last = timeline[-1] if timeline else None
        if last and last.get("type") == "thinking":
            nextTimeline = list(timeline)
            nextTimeline[-1] = {**last, "content": event.get("token", "")}
            return nextTimeline
        return timeline

    if eventType == "thinking_to_answer":
        # 流末判定为最终回答：将末尾 thinking item 与 answer 匹配的部分移出（置 done）
        last = timeline[-1] if timeline else None
        answer = event.get("answer")
        if last and last.get("type") == "thinking" and answer:
            idx = last["content"].rfind(answer)
            if idx >= 0:
                nextTimeline = list(timeline)
                nextTimeline[-1] = {**last, "content": last["content"][:idx], "done": True}
                return nextTimeline
        return timeline

    if eventType == "search_start":
        return [
            *timeline,
            {"type": "search", "query": event.get("query"), "status": "searching"},
        ]

    if eventType == "search_result":
        # 更新最近的 searching 状态 search item 为 done 并写入结果
        nextTimeline = list(timeline)
        for i in range(len(nextTimeline) - 1, -1, -1):
            item = nextTimeline[i]
            if item.get("type") == "search" and item.get("status") == "searching":
                nextTimeline[i] = {**item, "status": "done", "results": event.get("results") or []}
                return nextTimeline
        # 无 searching item（容错）：新建 done item
        return [
            *timeline,
            {
                "type": "search",
                "query": event.get("query"),
                "status": "done",
                "results": event.get("results") or [],
            },
        ]

    if eventType == "search_error":
        nextTimeline = list(timeline)
        for i in range(len(nextTimeline) - 1, -1, -1):
            item = nextTimeline[i]
            if item.get("type") == "search" and item.get("status") == "searching":
                nextTimeline[i] = {**item, "status": "error"}
                return nextTimeline
        return timeline

    if eventType == "tool_call":
        # 搜索类工具由 search_* 事件驱动 SearchBanner，不生成 tool_call item
        if event.get("name") in SEARCH_TOOL_NAMES:
            return timeline
        # 思考后接工具调用：末尾未完成 thinking item 显式收口
        return [
            *close_last_thinking(timeline),
            {
                "type": "tool_call",
                "name": event.get("name"),
                "args": summarize_tool_args(event.get("args")),
                "done": False,
            },
        ]

    if eventType == "tool_result":
        # 搜索类工具结果由 search_result 事件驱动，不进入 tool_call item
        if event.get("name") in SEARCH_TOOL_NAMES:
            return timeline
        resultSummary = summarize_tool_result(event.get("result"))
        nextTimeline = list(timeline)
        # 优先：同名且 done 为假值的最近 item
        idx = -1
        for i in range(len(nextTimeline) - 1, -1, -1):
            item = nextTimeline[i]
            if (
                item.get("type") == "tool_call"
                and item.get("name") == event.get("name")
                and not item.get("done")
            ):
                idx = i
                break
        # 回退：最近未完成的任意 tool_call item
        if idx == -1:
            for i in range(len(nextTimeline) - 1, -1, -1):
                item = nextTimeline[i]
                if item.get("type") == "tool_call" and not item.get("done"):
                    idx = i
                    break
        if idx >= 0:
            item = nextTimeline[idx]
            if item.get("type") == "tool_call":
                nextTimeline[idx] = {**item, "result": resultSummary, "done": True}
            return nextTimeline
        # 无匹配且结果非空：新建仅含结果的 item
        if resultSummary:
            return [
                *timeline,
                {
                    "type": "tool_call",
                    "name": event.get("name"),
                    "args": "",
                    "result": resultSummary,
                    "done": True,
                },
            ]
        return timeline

    if eventType == "chat_token":
        # 思考后接回答：末尾未完成 thinking item 显式收口
        return close_last_thinking(timeline)

    if eventType == "chat_done":
        # 流式结束：所有 thinking item 收口；无 title 时提取 ## 标题写入 title
        return [
            {**item, "title": extract_thinking_title(item.get("content", ""))}
            if item.get("type") == "thinking" and "title" not in item
            else item
            for item in close_all_thinking(timeline)
        ]

    if eventType == "error":
        return close_all_thinking(timeline)

    return timeline
