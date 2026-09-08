# 人工验证报告: remove-fake-stream-events

**日期**: 2026-09-06
**验证人**: ZCode agent（真实 LLM 流式实测 + 行为回归测试）
**关联 delta**: openspec/changes/remove-fake-stream-events/
**E2E 门禁**: stub 套件 `npx playwright test --grep-invert "@live"` → 20 passed / 2 skipped / 0 failed（2026-09-06，后端自建 TESTING 实例）

## 删除内容

- ① `_run_react_analysis` 预搜索块：伪 thinking_token（"我先搜索最新市场信息"）+ 伪 tool_call/tool_result + 手工 search_start/search_result + 搜索结果注入用户消息（约 82 行）
- ② `_run_graph_streaming` 节点开始伪思考（`▶ 正在执行…`）
- ③ 节点完成摘要伪思考（`✓ …`）
- `_NODE_THINKING` 常量与 `_TIME_SENSITIVE_KEYWORDS_REACT` 死导入

## 验证结果

| 验证项 | 方式 | 实际结果 | 通过 |
|---|---|---|---|
| ① 时效性查询无预搜索事件 | 行为回归测试（test_timesensitive_query_no_presearch_events，先红后绿）：模型收到的用户消息无搜索注入，发布流无伪 token/tool_call | 断言通过 | ✅ |
| ② ③ 管线流无 ▶/✓ 伪 thinking | 行为回归测试（test_pipeline_stream_no_fake_node_thinking，先红后绿） | 无 ▶/✓ token；节点真实 thinking（custom mode）照常转发；report_ready 正常 | ✅ |
| 真实 LLM 时效性查询自主搜索 | 真实流式实测（阿里云 deepseek-v4-flash-0731，query=最近有什么热门股票，426 事件） | 预搜索特征 **0**（无"我先搜索…"、无 ▶/✓）；模型真实推理（英文 reasoning 流）后**自主调用 web_search**，真实 search_start/search_result/tool_call/tool_result 齐备，进入澄清等待 | ✅ |
| 前端回归 | vitest 全量 | 490/490 | ✅ |
| E2E stub 门禁 | playwright --grep-invert @live | 20 passed / 2 skipped / 0 failed | ✅ |
| 后端全量 | pytest -m 'not live' | 1983 passed / 2 failed——**该 2 失败经 git stash 对照确认为工作区并行会话既有失败（HEAD 同样失败），与本 delta 无关** | ✅（不引入回归） |

## 备注

- quick 模式搜索横幅由 agent 工具路径的 search_start 驱动（agent_factory:1437），删除预搜索后横幅语义不变，仅来源从"系统预生成"变为"模型真实调用"。
- 原 transparent-system-events delta 已标记 superseded 移入 archive（诉求以删除方式达成）。

## 结论

- [x] 全部通过，可 archive（任务 6/6）
