"""后端 agentTimeline 构建器测试 —— 逐行镜像 frontend/src/timeline.ts 的 applyChatStreamEvent 语义。

测试事件结构与前端 SSEEvent 对齐（type/token/name/args/result/query/results/message 字段）。
断言只针对 timeline 部分（chatResponse 等由调用方处理，不在 apply_chat_event 职责内）。
"""

# 测试方法名使用中文描述（含 ASCII 大写片段如 token/search_start），
# pep8-naming N802/N806 不适用于中文测试名与 camelCase 变量（项目规范），模块级豁免
# ruff: noqa: N802, N806

from __future__ import annotations

import pytest

from finance_agent.timeline_builder import (
    SEARCH_TOOL_NAMES,
    append_thinking_token,
    apply_chat_event,
    apply_pipeline_node_complete,
    apply_pipeline_search_event,
    apply_pipeline_thinking_token,
    apply_pipeline_tool_event,
    close_all_thinking,
    close_last_thinking,
    extract_thinking_title,
    summarize_tool_args,
    summarize_tool_result,
)

# ── 基础工具函数 ──────────────────────────────────────────────


class TestSearchToolNames:
    def test_包含两个搜索工具(self):
        assert {"web_search", "batch_web_search"} == SEARCH_TOOL_NAMES


class TestAppendThinkingToken:
    def test_空timeline新建thinking片段(self):
        timeline = append_thinking_token([], "你好")
        assert timeline == [{"type": "thinking", "content": "你好", "done": False}]

    def test_末尾thinking累加content(self):
        timeline = [{"type": "thinking", "content": "你好", "done": False}]
        timeline = append_thinking_token(timeline, "世界")
        assert timeline == [{"type": "thinking", "content": "你好世界", "done": False}]

    def test_末尾已完成thinking仍累加(self):
        # 前端只判断 type === 'thinking'，不看 done
        timeline = [{"type": "thinking", "content": "你好", "done": True}]
        timeline = append_thinking_token(timeline, "!")
        assert timeline == [{"type": "thinking", "content": "你好!", "done": True}]

    def test_末尾非thinking新建片段(self):
        timeline = [{"type": "search", "query": "q", "status": "searching"}]
        timeline = append_thinking_token(timeline, "思考")
        assert timeline[-1] == {"type": "thinking", "content": "思考", "done": False}
        assert len(timeline) == 2

    def test_不可变更新不修改原列表(self):
        original = [{"type": "thinking", "content": "a", "done": False}]
        newTimeline = append_thinking_token(original, "b")
        assert original == [{"type": "thinking", "content": "a", "done": False}]
        assert newTimeline is not original


class TestCloseLastThinking:
    def test_末尾未完成thinking置done(self):
        timeline = [{"type": "thinking", "content": "a", "done": False}]
        result = close_last_thinking(timeline)
        assert result[-1]["done"] is True

    def test_末尾已完成thinking不变(self):
        timeline = [{"type": "thinking", "content": "a", "done": True}]
        result = close_last_thinking(timeline)
        assert result[-1]["done"] is True
        assert result is timeline  # 前端同引用返回

    def test_末尾非thinking原样返回(self):
        timeline = [{"type": "tool_call", "name": "x", "args": "", "done": False}]
        result = close_last_thinking(timeline)
        assert result is timeline

    def test_只关末尾不关中间(self):
        timeline = [
            {"type": "thinking", "content": "a", "done": False},
            {"type": "search", "query": "q", "status": "done"},
        ]
        result = close_last_thinking(timeline)
        assert result[0]["done"] is False  # 中间未完成 thinking 不受影响


class TestCloseAllThinking:
    def test_所有未完成thinking置done(self):
        timeline = [
            {"type": "thinking", "content": "a", "done": False},
            {"type": "search", "query": "q", "status": "done"},
            {"type": "thinking", "content": "b", "done": False},
            {"type": "thinking", "content": "c", "done": True},
        ]
        result = close_all_thinking(timeline)
        assert result[0]["done"] is True
        assert result[2]["done"] is True
        assert result[3]["done"] is True
        assert result[1]["status"] == "done"  # search 项不受影响


class TestExtractThinkingTitle:
    def test_提取首个二级标题(self):
        assert extract_thinking_title("## 分析茅台\n正文") == "分析茅台"

    def test_标题前后空白被去除(self):
        assert extract_thinking_title("  ##   多空辩论  \n正文") == "多空辩论"

    def test_multiline取首个标题(self):
        content = "前言\n## 第一个\n## 第二个\n"
        assert extract_thinking_title(content) == "第一个"

    def test_无标题返回None(self):
        assert extract_thinking_title("没有标题的正文") is None

    def test_空字符串返回None(self):
        assert extract_thinking_title("") is None

    def test_井号后无空格不匹配(self):
        # 正则要求 ## 后至少一个空白
        assert extract_thinking_title("##无空格") is None


class TestSummarizeToolResult:
    def test_字符串截断150(self):
        assert summarize_tool_result("x" * 200) == "x" * 150

    def test_短字符串原样(self):
        assert summarize_tool_result("结果") == "结果"

    def test_list取前三项title(self):
        result = [
            {"title": "标题1"},
            {"title": "标题2"},
            {"title": "标题3"},
            {"title": "标题4"},
        ]
        assert summarize_tool_result(result) == "标题1、标题2、标题3"

    def test_list回退name和code(self):
        result = [{"name": "名称"}, {"code": "600519"}]
        assert summarize_tool_result(result) == "名称、600519"

    def test_list无title_name_code时json截断50(self):
        result = [{"foo": "bar"}]
        assert summarize_tool_result(result) == '{"foo": "bar"}'

    def test_list元素含None不崩溃(self):
        # 前端 (r as Record)?.title 对 null 返回 undefined，走 JSON.stringify 分支
        result = [None, {"title": "有标题"}]
        assert summarize_tool_result(result) == "null、有标题"

    def test_dict转json截断150(self):
        result = {"key": "v" * 300}
        out = summarize_tool_result(result)
        assert len(out) == 150

    def test_其他类型返回空串(self):
        assert summarize_tool_result(123) == ""
        assert summarize_tool_result(None) == ""
        assert summarize_tool_result(True) == ""


class TestSummarizeToolArgs:
    def test_None返回空串(self):
        assert summarize_tool_args(None) == ""

    def test_query优先(self):
        assert summarize_tool_args({"query": "茅台 新闻", "other": 1}) == "茅台 新闻"

    def test_queries用顿号连接(self):
        assert summarize_tool_args({"queries": ["q1", "q2"]}) == "q1、q2"

    def test_其余非空dict转json(self):
        out = summarize_tool_args({"code": "600519"})
        assert "600519" in out

    def test_空dict返回空串(self):
        assert summarize_tool_args({}) == ""

    def test_query非str走后续分支(self):
        out = summarize_tool_args({"query": 123, "code": "x"})
        assert "123" in out  # JSON 序列化整个 dict


# ── apply_chat_event 主函数 ──────────────────────────────────


class TestThinkingToken:
    def test_追加thinking_token(self):
        timeline = apply_chat_event([], {"type": "thinking_token", "token": "思"})
        assert timeline == [{"type": "thinking", "content": "思", "done": False}]

    def test_连续token累加(self):
        timeline = []
        for token in ["思", "考", "中"]:
            timeline = apply_chat_event(timeline, {"type": "thinking_token", "token": token})
        assert timeline == [{"type": "thinking", "content": "思考中", "done": False}]


class TestThinkingReplace:
    def test_替换末尾thinking内容(self):
        timeline = [{"type": "thinking", "content": "原始", "done": False}]
        result = apply_chat_event(timeline, {"type": "thinking_replace", "token": "清理后"})
        assert result == [{"type": "thinking", "content": "清理后", "done": False}]

    def test_末尾非thinking原样返回(self):
        timeline = [{"type": "search", "query": "q", "status": "done"}]
        result = apply_chat_event(timeline, {"type": "thinking_replace", "token": "x"})
        assert result is timeline


class TestThinkingToAnswer:
    def test_末尾thinking截断并收口(self):
        timeline = [{"type": "thinking", "content": "思考前缀最终回答", "done": False}]
        result = apply_chat_event(timeline, {"type": "thinking_to_answer", "answer": "最终回答"})
        assert result == [{"type": "thinking", "content": "思考前缀", "done": True}]

    def test_answer不在content中原样返回(self):
        timeline = [{"type": "thinking", "content": "只有思考", "done": False}]
        result = apply_chat_event(
            timeline, {"type": "thinking_to_answer", "answer": "不存在的回答"}
        )
        assert result is timeline

    def test_无answer原样返回(self):
        timeline = [{"type": "thinking", "content": "思考", "done": False}]
        result = apply_chat_event(timeline, {"type": "thinking_to_answer"})
        assert result is timeline


class TestSearchEvents:
    def test_search_start追加searching(self):
        timeline = apply_chat_event([], {"type": "search_start", "query": "茅台 最新消息"})
        assert timeline == [{"type": "search", "query": "茅台 最新消息", "status": "searching"}]

    def test_search_result更新最近searching为done(self):
        timeline = [
            {"type": "search", "query": "q1", "status": "searching"},
        ]
        results = [{"title": "t", "url": "u", "content": "c"}]
        timeline = apply_chat_event(
            timeline, {"type": "search_result", "query": "q1", "results": results}
        )
        assert timeline[0]["status"] == "done"
        assert timeline[0]["results"] == results

    def test_search_result无searching时追加done项(self):
        timeline = [{"type": "thinking", "content": "a", "done": False}]
        results = [{"title": "t", "url": "u", "content": "c"}]
        timeline = apply_chat_event(
            timeline, {"type": "search_result", "query": "q2", "results": results}
        )
        assert timeline[-1] == {
            "type": "search",
            "query": "q2",
            "status": "done",
            "results": results,
        }

    def test_search_result更新最近的searching而非较早的(self):
        timeline = [
            {"type": "search", "query": "q1", "status": "searching"},
            {"type": "search", "query": "q2", "status": "searching"},
        ]
        timeline = apply_chat_event(
            timeline, {"type": "search_result", "query": "q2", "results": []}
        )
        assert timeline[0]["status"] == "searching"
        assert timeline[1]["status"] == "done"

    def test_search_result_results缺省为空列表(self):
        timeline = [{"type": "search", "query": "q", "status": "searching"}]
        timeline = apply_chat_event(timeline, {"type": "search_result", "query": "q"})
        assert timeline[0]["results"] == []

    def test_search_error更新最近searching为error(self):
        timeline = [{"type": "search", "query": "q", "status": "searching"}]
        timeline = apply_chat_event(timeline, {"type": "search_error", "message": "超时"})
        assert timeline[0]["status"] == "error"

    def test_search_error无searching原样返回(self):
        timeline = [{"type": "search", "query": "q", "status": "done"}]
        result = apply_chat_event(timeline, {"type": "search_error", "message": "x"})
        assert result is timeline


class TestToolCall:
    def test_搜索类tool_call被跳过(self):
        timeline = [{"type": "thinking", "content": "a", "done": False}]
        for name in ("web_search", "batch_web_search"):
            result = apply_chat_event(timeline, {"type": "tool_call", "name": name, "args": {}})
            assert result is timeline

    def test_普通tool_call收口thinking并追加(self):
        timeline = [{"type": "thinking", "content": "a", "done": False}]
        result = apply_chat_event(
            timeline,
            {"type": "tool_call", "name": "search_stock", "args": {"query": "茅台"}},
        )
        assert result[0]["done"] is True
        assert result[1] == {
            "type": "tool_call",
            "name": "search_stock",
            "args": "茅台",
            "done": False,
        }

    def test_tool_call_args摘要(self):
        timeline = []
        result = apply_chat_event(
            timeline,
            {"type": "tool_call", "name": "get_metrics", "args": {"code": "600519"}},
        )
        assert result[0]["type"] == "tool_call"
        assert "600519" in result[0]["args"]


class TestToolResult:
    def test_搜索类tool_result被跳过(self):
        timeline = [{"type": "search", "query": "q", "status": "searching"}]
        result = apply_chat_event(
            timeline,
            {"type": "tool_result", "name": "web_search", "result": "搜索结果"},
        )
        assert result is timeline

    def test_优先回填同名未完成item(self):
        timeline = [
            {"type": "tool_call", "name": "a_tool", "args": "", "done": False},
            {"type": "tool_call", "name": "b_tool", "args": "", "done": False},
        ]
        result = apply_chat_event(
            timeline,
            {"type": "tool_result", "name": "a_tool", "result": "结果A"},
        )
        assert result[0]["result"] == "结果A"
        assert result[0]["done"] is True
        assert result[1]["done"] is False  # b_tool 不受影响

    def test_回退到最近未完成item(self):
        timeline = [
            {"type": "tool_call", "name": "a_tool", "args": "", "done": False},
        ]
        result = apply_chat_event(
            timeline,
            {"type": "tool_result", "name": "unknown_tool", "result": "结果"},
        )
        assert result[0]["result"] == "结果"
        assert result[0]["done"] is True

    def test_无匹配且结果非空追加仅结果项(self):
        timeline = [{"type": "thinking", "content": "a", "done": True}]
        result = apply_chat_event(
            timeline,
            {"type": "tool_result", "name": "x_tool", "result": "结果文本"},
        )
        assert result[-1] == {
            "type": "tool_call",
            "name": "x_tool",
            "args": "",
            "result": "结果文本",
            "done": True,
        }

    def test_无匹配且结果为空原样返回(self):
        timeline = [{"type": "thinking", "content": "a", "done": True}]
        result = apply_chat_event(
            timeline, {"type": "tool_result", "name": "x_tool", "result": 123}
        )
        assert result is timeline

    def test_结果摘要截断(self):
        timeline = [{"type": "tool_call", "name": "t", "args": "", "done": False}]
        result = apply_chat_event(
            timeline,
            {"type": "tool_result", "name": "t", "result": "x" * 300},
        )
        assert result[0]["result"] == "x" * 150


class TestChatToken:
    def test_chat_token收口末尾thinking(self):
        timeline = [{"type": "thinking", "content": "a", "done": False}]
        result = apply_chat_event(timeline, {"type": "chat_token", "token": "答"})
        assert result[0]["done"] is True

    def test_chat_token不影响非thinking末尾(self):
        timeline = [{"type": "search", "query": "q", "status": "done"}]
        result = apply_chat_event(timeline, {"type": "chat_token", "token": "答"})
        assert result is timeline


class TestChatDone:
    def test_收口所有thinking并补title(self):
        timeline = [
            {"type": "thinking", "content": "## 阶段一\n内容一", "done": False},
            {"type": "tool_call", "name": "t", "args": "", "done": True},
            {"type": "thinking", "content": "无标题内容", "done": False},
        ]
        result = apply_chat_event(timeline, {"type": "chat_done"})
        assert result[0]["done"] is True
        assert result[0]["title"] == "阶段一"
        assert result[2]["done"] is True
        assert result[2]["title"] is None

    def test_已有title不被覆盖(self):
        timeline = [
            {"type": "thinking", "content": "## 新标题", "done": False, "title": "旧标题"},
        ]
        result = apply_chat_event(timeline, {"type": "chat_done"})
        assert result[0]["title"] == "旧标题"


class TestError:
    def test_error收口所有thinking(self):
        timeline = [
            {"type": "thinking", "content": "a", "done": False},
            {"type": "thinking", "content": "b", "done": False},
        ]
        result = apply_chat_event(timeline, {"type": "error", "message": "失败"})
        assert all(item["done"] is True for item in result)


class TestUnknownEvent:
    def test_未知事件原样返回(self):
        timeline = [{"type": "thinking", "content": "a", "done": False}]
        result = apply_chat_event(timeline, {"type": "node_start", "node_id": "x"})
        assert result is timeline


# ── 断开-新建语义（design.md 决策 2）─────────────────────────


class TestThinkingSegmentation:
    def test_tool_call后再thinking新建片段(self):
        timeline = []
        timeline = apply_chat_event(timeline, {"type": "thinking_token", "token": "第一段"})
        timeline = apply_chat_event(
            timeline,
            {"type": "tool_call", "name": "search_stock", "args": {"query": "茅台"}},
        )
        timeline = apply_chat_event(timeline, {"type": "thinking_token", "token": "第二段"})
        assert len(timeline) == 3
        assert timeline[0] == {"type": "thinking", "content": "第一段", "done": True}
        assert timeline[1]["type"] == "tool_call"
        assert timeline[2] == {"type": "thinking", "content": "第二段", "done": False}

    def test_search_start后再thinking新建片段(self):
        timeline = []
        timeline = apply_chat_event(timeline, {"type": "thinking_token", "token": "思考"})
        timeline = apply_chat_event(timeline, {"type": "search_start", "query": "q"})
        timeline = apply_chat_event(timeline, {"type": "thinking_token", "token": "继续"})
        assert len(timeline) == 3
        assert timeline[2]["content"] == "继续"


# ── 与前端 applyChatStreamEvent 同事件序列一致性 ─────────────


class TestFrontendParity:
    """用一组代表性事件序列，断言最终 timeline 结构与前端 applyChatStreamEvent 产出一致。

    期望值按 frontend/src/timeline.ts 逐分支推演得出（不经过后端实现的中间推理）。
    """

    def test_完整对话流事件序列(self):
        events = [
            {"type": "thinking_token", "token": "我先搜索一下。"},
            {"type": "tool_call", "name": "web_search", "args": {"query": "茅台 最新"}},
            {"type": "search_start", "query": "茅台 最新"},
            {"type": "tool_result", "name": "web_search", "result": "搜索结果文本"},
            {
                "type": "search_result",
                "query": "茅台 最新",
                "results": [{"title": "新闻A", "url": "u1", "content": "c1"}],
            },
            {"type": "thinking_token", "token": "## 分析\n根据搜索结果"},
            {"type": "tool_call", "name": "search_stock", "args": {"query": "贵州茅台"}},
            {"type": "tool_result", "name": "search_stock", "result": {"code": "600519"}},
            {"type": "chat_token", "token": "结论是"},
            {"type": "chat_token", "token": "买入。"},
            {"type": "chat_done"},
        ]
        timeline: list[dict] = []
        for event in events:
            timeline = apply_chat_event(timeline, event)

        # 按前端语义推演的期望 timeline
        assert timeline == [
            # 1. thinking_token 新建；web_search 的 tool_call 被跳过（搜索类），
            #    search_start 追加 search 项断开 thinking；chat_done 收口所有 thinking 并补 title
            {"type": "thinking", "content": "我先搜索一下。", "done": True, "title": None},
            # 2. search_start -> searching；search_result -> done + results
            {
                "type": "search",
                "query": "茅台 最新",
                "status": "done",
                "results": [{"title": "新闻A", "url": "u1", "content": "c1"}],
            },
            # 3. thinking_token 新建片段（末尾非 thinking）；chat_done 收口 + 补 title
            {"type": "thinking", "content": "## 分析\n根据搜索结果", "done": True, "title": "分析"},
            # 4. search_stock tool_call（closeLastThinking 无效果——末尾已是 thinking done=False? 否：
            #    此时末尾是第二个 thinking（未完成），tool_call 将其收口）
            {
                "type": "tool_call",
                "name": "search_stock",
                "args": "贵州茅台",
                "result": '{"code": "600519"}',
                "done": True,
            },
        ]

    def test_thinking_replace与thinking_to_answer序列(self):
        events = [
            {"type": "thinking_token", "token": "<dsml>原始思考最终答案"},
            {"type": "thinking_replace", "token": "清理后的思考最终答案"},
            {"type": "thinking_to_answer", "answer": "最终答案"},
            {"type": "chat_done"},
        ]
        timeline: list[dict] = []
        for event in events:
            timeline = apply_chat_event(timeline, event)
        assert timeline == [
            {"type": "thinking", "content": "清理后的思考", "done": True, "title": None}
        ]

    def test_不可变性_原timeline不被修改(self):
        original = [{"type": "thinking", "content": "a", "done": False}]
        snapshot = [dict(item) for item in original]
        apply_chat_event(original, {"type": "thinking_token", "token": "b"})
        apply_chat_event(original, {"type": "chat_done"})
        assert original == snapshot


# ── 管线分组件（nodeTimelines，镜像 applyPipelineThinkingToken / applyPipelineNodeComplete）──


class TestApplyPipelineThinkingToken:
    def test_空分组新建节点thinking(self):
        result = apply_pipeline_thinking_token({}, "check_cache", "思")
        assert result == {"check_cache": [{"type": "thinking", "content": "思", "done": False}]}

    def test_同节点token累加(self):
        timelines: dict = {}
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "思")
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "考")
        assert timelines["check_cache"] == [{"type": "thinking", "content": "思考", "done": False}]

    def test_按节点分组互不干扰(self):
        timelines: dict = {}
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "缓存")
        timelines = apply_pipeline_thinking_token(timelines, "fetch_data", "行情")
        assert timelines["check_cache"][0]["content"] == "缓存"
        assert timelines["fetch_data"][0]["content"] == "行情"

    def test_跨节点防御性收口其他节点thinking(self):
        # 新节点 thinking_token 到达时，其他节点末尾未完成 thinking 置 done
        timelines: dict = {}
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "缓存")
        timelines = apply_pipeline_thinking_token(timelines, "fetch_data", "行情")
        assert timelines["check_cache"][0]["done"] is True
        assert timelines["fetch_data"][0]["done"] is False

    def test_防御性收口不影响其他节点末尾非thinking(self):
        timelines = {
            "check_cache": [{"type": "search", "query": "q", "status": "searching"}],
        }
        result = apply_pipeline_thinking_token(timelines, "fetch_data", "思")
        assert result["check_cache"][0]["status"] == "searching"

    def test_回到旧节点继续累加(self):
        timelines: dict = {}
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "缓存")
        timelines = apply_pipeline_thinking_token(timelines, "fetch_data", "行情")
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "继续")
        # fetch_data 被防御性收口；check_cache 末尾 thinking 已 done 仍累加（前端语义）
        assert timelines["fetch_data"][0]["done"] is True
        assert timelines["check_cache"][0]["content"] == "缓存继续"

    def test_node空串归入空键(self):
        result = apply_pipeline_thinking_token({}, "", "未分组")
        assert result[""] == [{"type": "thinking", "content": "未分组", "done": False}]

    def test_node为None归入空键(self):
        # 前端 event.node || '' 语义
        result = apply_pipeline_thinking_token({}, None, "未分组")
        assert result[""] == [{"type": "thinking", "content": "未分组", "done": False}]

    def test_不可变更新不修改原dict(self):
        original = {"check_cache": [{"type": "thinking", "content": "a", "done": False}]}
        snapshot = {k: [dict(item) for item in v] for k, v in original.items()}
        result = apply_pipeline_thinking_token(original, "check_cache", "b")
        assert original == snapshot
        assert result is not original
        assert result["check_cache"] is not original["check_cache"]


class TestApplyPipelineNodeComplete:
    def test_该节点末尾未完成thinking置done(self):
        timelines = {"check_cache": [{"type": "thinking", "content": "a", "done": False}]}
        result = apply_pipeline_node_complete(timelines, "check_cache")
        assert result["check_cache"][0]["done"] is True

    def test_无该节点原样返回(self):
        timelines = {"check_cache": [{"type": "thinking", "content": "a", "done": False}]}
        result = apply_pipeline_node_complete(timelines, "fetch_data")
        assert result is timelines

    def test_空分组原样返回(self):
        timelines: dict = {}
        result = apply_pipeline_node_complete(timelines, "check_cache")
        assert result is timelines

    def test_该节点末尾已完成thinking不变(self):
        timelines = {"check_cache": [{"type": "thinking", "content": "a", "done": True}]}
        result = apply_pipeline_node_complete(timelines, "check_cache")
        assert result["check_cache"][0]["done"] is True
        assert result["check_cache"] is timelines["check_cache"]  # 无变化返回同引用

    def test_不影响其他节点(self):
        timelines = {
            "check_cache": [{"type": "thinking", "content": "a", "done": False}],
            "fetch_data": [{"type": "thinking", "content": "b", "done": False}],
        }
        result = apply_pipeline_node_complete(timelines, "check_cache")
        assert result["check_cache"][0]["done"] is True
        assert result["fetch_data"][0]["done"] is False

    def test_不可变更新不修改原dict(self):
        original = {"check_cache": [{"type": "thinking", "content": "a", "done": False}]}
        snapshot = {k: [dict(item) for item in v] for k, v in original.items()}
        result = apply_pipeline_node_complete(original, "check_cache")
        assert original == snapshot
        assert result is not original


class TestPipelineTimelineSequence:
    """模拟真实管线事件序列：thinking_token（带 node）+ node_complete 的组合行为。"""

    def test_节点完成收口后新节点开始(self):
        timelines: dict = {}
        # check_cache 节点思考
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "读取缓存")
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "…命中")
        # 节点完成收口
        timelines = apply_pipeline_node_complete(timelines, "check_cache")
        assert timelines["check_cache"][0] == {
            "type": "thinking",
            "content": "读取缓存…命中",
            "done": True,
        }
        # fetch_data 节点思考（check_cache 已收口，防御性收口为无操作）
        timelines = apply_pipeline_thinking_token(timelines, "fetch_data", "拉取行情")
        assert timelines["fetch_data"][0]["content"] == "拉取行情"
        assert timelines["fetch_data"][0]["done"] is False

    def test_node_complete缺失时防御性收口兜底(self):
        # 节点未发 node_complete 直接切到下一节点（异常路径），
        # 新节点 thinking_token 触发防御性收口
        timelines: dict = {}
        timelines = apply_pipeline_thinking_token(timelines, "check_cache", "未收口")
        timelines = apply_pipeline_thinking_token(timelines, "fetch_data", "新节点")
        assert timelines["check_cache"][0]["done"] is True


# ── 管线 search/tool 事件按当前运行节点归属（persist-full-session-timeline）──


class TestApplyPipelineSearchEvent:
    """apply_pipeline_search_event：search_* 三态应用到指定节点的 timeline。"""

    def test_search_start归属当前节点(self):
        result = apply_pipeline_search_event(
            {}, "check_cache", {"type": "search_start", "query": "茅台"}
        )
        assert result == {
            "check_cache": [{"type": "search", "query": "茅台", "status": "searching"}]
        }

    def test_search_result回填该节点最近searching(self):
        timelines = {
            "check_cache": [{"type": "search", "query": "q", "status": "searching"}],
        }
        result = apply_pipeline_search_event(
            timelines,
            "check_cache",
            {"type": "search_result", "query": "q", "results": [{"title": "t"}]},
        )
        assert result["check_cache"] == [
            {"type": "search", "query": "q", "status": "done", "results": [{"title": "t"}]}
        ]

    def test_search_error置该节点error(self):
        timelines = {
            "check_cache": [{"type": "search", "query": "q", "status": "searching"}],
        }
        result = apply_pipeline_search_event(
            timelines, "check_cache", {"type": "search_error", "message": "超时"}
        )
        assert result["check_cache"][0]["status"] == "error"

    def test_不影响其他节点(self):
        timelines = {
            "check_cache": [{"type": "thinking", "content": "a", "done": False}],
        }
        result = apply_pipeline_search_event(
            timelines, "fetch_data", {"type": "search_start", "query": "q"}
        )
        # 其他节点原样（不触发防御性收口——与 apply_pipeline_thinking_token 不同，
        # search/tool 事件不跨节点收口，仅作用于归属节点）
        assert result["check_cache"][0]["done"] is False
        assert result["fetch_data"][0]["type"] == "search"

    def test_node空串归入空键(self):
        result = apply_pipeline_search_event({}, "", {"type": "search_start", "query": "q"})
        assert result[""] == [{"type": "search", "query": "q", "status": "searching"}]

    def test_node为None归入空键(self):
        result = apply_pipeline_search_event({}, None, {"type": "search_start", "query": "q"})
        assert result[""][0]["status"] == "searching"

    def test_不可变更新不修改原dict(self):
        original = {"check_cache": [{"type": "search", "query": "q", "status": "searching"}]}
        snapshot = {k: [dict(item) for item in v] for k, v in original.items()}
        result = apply_pipeline_search_event(
            original, "check_cache", {"type": "search_result", "query": "q", "results": []}
        )
        assert original == snapshot
        assert result is not original


class TestApplyPipelineToolEvent:
    """apply_pipeline_tool_event：tool_call/tool_result 应用到指定节点的 timeline。"""

    def test_tool_call收口该节点末尾thinking并追加(self):
        timelines = {
            "check_cache": [{"type": "thinking", "content": "思考", "done": False}],
        }
        result = apply_pipeline_tool_event(
            timelines,
            "check_cache",
            {"type": "tool_call", "name": "search_stock", "args": {"query": "茅台"}},
        )
        assert result["check_cache"] == [
            {"type": "thinking", "content": "思考", "done": True},
            {"type": "tool_call", "name": "search_stock", "args": "茅台", "done": False},
        ]

    def test_搜索类tool_call跳过不生成item(self):
        for name in ("web_search", "batch_web_search"):
            result = apply_pipeline_tool_event(
                {}, "check_cache", {"type": "tool_call", "name": name, "args": {"query": "q"}}
            )
            assert result == {"check_cache": []}

    def test_tool_result同名回填(self):
        timelines = {
            "check_cache": [
                {"type": "tool_call", "name": "search_stock", "args": "茅台", "done": False}
            ],
        }
        result = apply_pipeline_tool_event(
            timelines,
            "check_cache",
            {"type": "tool_result", "name": "search_stock", "result": "找到了"},
        )
        assert result["check_cache"][0]["result"] == "找到了"
        assert result["check_cache"][0]["done"] is True

    def test_tool_result无匹配新建仅结果项(self):
        result = apply_pipeline_tool_event(
            {}, "check_cache", {"type": "tool_result", "name": "t", "result": "结果文本"}
        )
        assert result["check_cache"] == [
            {"type": "tool_call", "name": "t", "args": "", "result": "结果文本", "done": True}
        ]

    def test_不影响其他节点(self):
        timelines = {
            "check_cache": [{"type": "thinking", "content": "a", "done": False}],
        }
        result = apply_pipeline_tool_event(
            timelines, "fetch_data", {"type": "tool_call", "name": "t", "args": {}}
        )
        assert result["check_cache"][0]["done"] is False
        assert result["fetch_data"][0]["type"] == "tool_call"

    def test_node空串归入空键(self):
        result = apply_pipeline_tool_event({}, "", {"type": "tool_call", "name": "t", "args": {}})
        assert result[""][0]["type"] == "tool_call"

    def test_不可变更新不修改原dict(self):
        original = {"check_cache": [{"type": "tool_call", "name": "t", "args": "", "done": False}]}
        snapshot = {k: [dict(item) for item in v] for k, v in original.items()}
        result = apply_pipeline_tool_event(
            original, "check_cache", {"type": "tool_result", "name": "t", "result": "r"}
        )
        assert original == snapshot
        assert result is not original


class TestPipelineSearchToolSequence:
    """search/tool 与 thinking 在节点 timeline 中的组合序列（镜像前端同构语义）。"""

    def test_thinking到search到tool到thinking分段(self):
        timelines: dict = {}
        timelines = apply_pipeline_thinking_token(timelines, "fetch_data", "先搜索")
        timelines = apply_pipeline_search_event(
            timelines, "fetch_data", {"type": "search_start", "query": "q"}
        )
        timelines = apply_pipeline_search_event(
            timelines, "fetch_data", {"type": "search_result", "query": "q", "results": []}
        )
        timelines = apply_pipeline_thinking_token(timelines, "fetch_data", "再调用工具")
        timelines = apply_pipeline_tool_event(
            timelines,
            "fetch_data",
            {"type": "tool_call", "name": "get_metrics", "args": {"code": "600519"}},
        )
        timelines = apply_pipeline_tool_event(
            timelines,
            "fetch_data",
            {"type": "tool_result", "name": "get_metrics", "result": {"pe": 20}},
        )
        timelines = apply_pipeline_node_complete(timelines, "fetch_data")
        assert timelines["fetch_data"] == [
            {"type": "thinking", "content": "先搜索", "done": False},
            {"type": "search", "query": "q", "status": "done", "results": []},
            {"type": "thinking", "content": "再调用工具", "done": True},
            {
                "type": "tool_call",
                "name": "get_metrics",
                "args": '{"code": "600519"}',
                "result": '{"pe": 20}',
                "done": True,
            },
        ]


# ── api._ChatCollector 集成 ──────────────────────────────────


class TestChatCollectorTimeline:
    """验证 _ChatCollector.feed 在保持既有字段行为的同时维护 agent_timeline。"""

    def _make_collector(self):
        from finance_agent.api import _ChatCollector

        return _ChatCollector()

    def test_初始为空timeline(self):
        collector = self._make_collector()
        assert collector.agent_timeline == []

    def test_feed_thinking与chat_token(self):
        collector = self._make_collector()
        collector.feed({"type": "thinking_token", "token": "思考中"})
        collector.feed({"type": "chat_token", "token": "回答"})
        assert collector.agent_timeline == [{"type": "thinking", "content": "思考中", "done": True}]
        # 既有字段行为保持不变
        assert collector.thinking == "思考中"
        assert collector.response == "回答"

    def test_feed_完整事件序列(self):
        collector = self._make_collector()
        events = [
            {"type": "thinking_token", "token": "先搜索。"},
            {"type": "tool_call", "name": "web_search", "args": {"query": "q"}},
            {"type": "search_start", "query": "q"},
            {"type": "search_result", "query": "q", "results": []},
            {"type": "thinking_token", "token": "再调用工具。"},
            {"type": "tool_call", "name": "search_stock", "args": {"query": "茅台"}},
            {"type": "tool_result", "name": "search_stock", "result": "找到了"},
            {"type": "chat_done"},
        ]
        for event in events:
            collector.feed(event)

        assert collector.agent_timeline == [
            # chat_done 收口所有未完成 thinking 并补 title（与前端一致）
            {"type": "thinking", "content": "先搜索。", "done": True, "title": None},
            {"type": "search", "query": "q", "status": "done", "results": []},
            {"type": "thinking", "content": "再调用工具。", "done": True, "title": None},
            {
                "type": "tool_call",
                "name": "search_stock",
                "args": "茅台",
                "result": "找到了",
                "done": True,
            },
        ]
        # 既有字段：web_search 也进 tool_calls（collector 不过滤搜索类，保持原行为）
        assert [tc["name"] for tc in collector.tool_calls] == ["web_search", "search_stock"]

    def test_feed_run_deep_analysis仍跳过tool_calls但进timeline(self):
        # run_deep_analysis 在 collector 既有逻辑中 return（不进 tool_calls），
        # 但 apply_chat_event 无此特例——timeline 应如实记录（与前端一致，
        # 前端跳过 tool_call item 仅因 isSearchToolName）。
        collector = self._make_collector()
        collector.feed(
            {"type": "tool_call", "name": "run_deep_analysis", "args": {"code": "600519"}}
        )
        assert collector.tool_calls == []
        assert collector.agent_timeline == [
            {
                "type": "tool_call",
                "name": "run_deep_analysis",
                "args": '{"code": "600519"}',
                "done": False,
            }
        ]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
