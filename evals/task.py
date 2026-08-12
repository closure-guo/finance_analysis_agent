# evals/task.py
"""实验 task 函数:按 item.input.mode 分派管线,输出 JSON 可序列化结果。

- deep:离线 graph.invoke(initial_state),judge_vars 经 extract_judge_vars 预提取
- quick:ReAct agent run_sync(quick 不进 5 层图,无辩论/决策层)
- follow_up / should_clarify:首版跳过(skipped 原因,不报错)

序列化铁律:不得把含 DataFrame 的原始 state 放进返回值。

设计说明:build_5layer_graph / build_agent / get_callback_handler 在模块级导入,
使测试可用 ``@patch("evals.task.build_5layer_graph")`` 等替换——mock.patch 的字符串
目标要求属性在模块命名空间存在(function-local 导入会令 patch 抛 AttributeError,
且即便 patch 成功也绕过 mock)。这三个符号无重名,模块级导入对业务零侵入
(`evals/` 不属 `src/finance_agent/`,仅单向消费业务 API)。
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.runnables import RunnableConfig

from evals.extract import extract_judge_vars
from finance_agent.agent_factory import build_agent
from finance_agent.graph import build_5layer_graph
from finance_agent.langfuse_tracing import get_callback_handler


def _run_deep(inp: dict) -> dict:
    graph = build_5layer_graph()
    initial_state = {
        "stock_code": inp["stock_code"],
        "stock_name": inp.get("stock_name", ""),
        "analysis_type": "comprehensive",
        "peer_codes": None,
        "enable_web_search": False,
        "api_key": None,
        "focus": inp.get("query"),
        "llm_config": None,
    }
    # langfuse 配置时注入回调,使管线 span 挂到实验 item trace 下;
    # 未配置时 get_callback_handler() 返回 None → config=None(零开销,业务无感知)
    handler = get_callback_handler()
    config: RunnableConfig | None = {"callbacks": [handler]} if handler else None
    state = graph.invoke(initial_state, config=config)
    return {
        "report": state.get("final_report"),
        "ticker": inp["stock_code"],
        "judge_vars": extract_judge_vars(state, query=inp.get("query", "")),
        "mode": "deep",
        "skipped": None,
    }


def _run_quick(inp: dict) -> dict:
    agent = build_agent(mode="quick", session_id=inp.get("session_id"))
    # Agent.run_sync 是 async def(harness/loop.py),用 asyncio.run 驱动;
    # 实验循环在同步上下文跑批,不引入 async 传染。
    answer = asyncio.run(agent.run_sync(inp["query"]))
    return {
        "report": answer,
        "ticker": inp.get("ticker"),
        "judge_vars": {"query": inp["query"], "report": answer or ""},
        "mode": "quick",
        "skipped": None,
    }


def run_task(*, item, expected_output: dict | None = None, **kwargs: Any) -> dict:
    """langfuse run_experiment TaskFunction 兼容签名(task(*, item, **kwargs))。

    item 可以是 DatasetItemClient(有 .input)或本地 dict(有 ["input"])。
    expected_output 优先取显式参数,其次 item.expected_output(DatasetItemClient
    自带),最后空 dict。should_clarify 项首版跳过(不进自动化实验)。
    """
    inp = item.input if hasattr(item, "input") else item["input"]
    exp = (
        expected_output
        or (item.expected_output if hasattr(item, "expected_output") else None)
        or {}
    )
    mode = inp.get("mode", "deep")
    if exp.get("should_clarify"):
        return {
            "report": None,
            "ticker": None,
            "judge_vars": {},
            "mode": mode,
            "skipped": "意图澄清项首版不进自动化实验",
        }
    if mode == "deep":
        return _run_deep(inp)
    if mode == "quick":
        return _run_quick(inp)
    return {
        "report": None,
        "ticker": None,
        "judge_vars": {},
        "mode": mode,
        "skipped": f"mode={mode} 首版不支持(follow_up 需 session fixture)",
    }
