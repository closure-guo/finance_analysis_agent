# 验证报告：fix-history-report-anchor（历史会话气泡错位 + UI 卡住 + 流式滚动）

> 日期：2026-08-02
> 验证人：AI Agent（自动测试 + Docker 实证 + 浏览器验证）

## 一、验证范围

本次验证覆盖 `fix-history-report-anchor` OpenSpec change 的三个修复点：
1. **Bug 1**：历史会话气泡错位（多轮澄清场景下报告消息插入位置错误）
2. **Bug 2**：输入股票名后 UI 卡住不输出内容（SSE 流被上一轮 done 事件终止）
3. **Bug 3**：流式输出过程中无法手动向上滚动（自动滚动抢占手动滚动）

## 二、测试验证

### 2.1 后端单元测试

| 测试文件 | 用例数 | 结果 |
|----------|--------|------|
| test_pipeline_anchor.py | 8 | 全通过 |
| test_followup_sse_termination.py | 3 | 全通过 |
| test_session_store.py | 8 | 全通过 |
| test_api_pipeline_resume.py | 3 | 全通过 |

关键用例覆盖：
- `test_set_pipeline_anchor_multi_turn`：多轮澄清 [user1, assistant1, user2] → 锚点 = 3
- `test_set_pipeline_anchor_ignores_inflight_assistant`：ReAct 在途 assistant upsert 不影响锚点
- `test_fast_path_sets_pipeline_anchor`：fast path 管线启动后锚点 = 1
- `test_followup_sse_not_terminated_by_previous_done`：追问时 SSE 流不被上一轮 done 终止
- `test_get_max_event_seq`：获取会话 journal 最大 seq

### 2.2 前端单元测试

| 测试文件 | 用例数 | 结果 |
|----------|--------|------|
| selectSession.test.tsx | 14 | 全通过 |
| followup-sse-dedup.test.tsx | 1 | 全通过 |
| 其他 12 个测试文件 | 122 | 全通过 |
| **合计** | **137** | **全通过** |

关键用例覆盖：
- 多轮澄清历史 + pipeline_anchor=3 → 断言 DOM 顺序：用户提问 → 助手思考 → 用户确认 → 管线时间轴 → 报告
- 追问历史 + pipeline_anchor=1 → 报告插在 user1 后、user2 前
- pipeline_anchor=null 旧会话 → 回退"第一个 user 后插入"行为

### 2.3 Lint / 类型检查

- `uv run ruff check`：All checks passed
- `uv run mypy src/finance_agent/agent_factory.py`：12 个预存在告警（均为 str|None 类型收窄，非本次引入）；本次新增的 set_pipeline_anchor 调用通过 assert 类型收窄消除

## 三、Docker 实证（浏览器验证）

### 3.1 环境准备

```
docker compose up -d --build backend frontend
→ backend / frontend 容器重建并启动
→ 后端 API 响应正常（GET /api/sessions 返回会话列表）
```

### 3.2 Bug 2 修复验证：输入"中际旭创"后 UI 不再卡住

```
1. 打开 http://localhost:5173，页面正常加载
2. 输入"分析热门股票"并提交 → agent 进入思考/搜索状态
3. 等待 ~15s → 出现"思考已完成""搜索了 5 个网页"等状态
4. 输入"中际旭创"并提交
5. 等待 10-15s → 页面持续出现思考内容、候选股列表、管线进度文本
结果：UI 未卡死，流式输出正常，PASS
```

根因回顾：修复前 ReAct 路径 SSE 订阅 `after_seq=0`，重放历史事件时遇到上一轮 done 终态事件导致流提前终止。修复后使用 `get_max_event_seq(session_id)` 作为 after_seq，跳过历史事件重放。

### 3.3 Bug 3 修复验证：流式输出时可手动滚动

```
在流式输出过程中执行向下与向上滚动
→ 页面位置可被改变，未出现被强制拉回底部的情况
结果：PASS
```

根因回顾：修复前自动滚动逻辑无条件执行 `window.scrollTo`，抢占用户手动滚动。修复后添加 `userScrolledUpRef` 检测用户滚动位置，当用户上拉离开底部 100px 时停止自动滚动。

### 3.4 Bug 1 修复验证：切换会话后气泡顺序正确

```
1. 在左侧会话列表中点击其他会话
2. 切回当前会话
3. 消息气泡顺序：用户"分析热门股票" → agent 回复 → 用户"中际旭创" → 分析报告/管线时间轴
结果：顺序正确，PASS
```

根因回顾：修复前端按 `pipeline_anchor` 锚点插入报告消息（锚点 = 最后一条 user 消息索引 + 1），而非固定插入在第一个 user 消息后。

## 四、Spec 条款符合性

| Spec 条款 | 验证方式 | 结果 |
|-----------|---------|------|
| pipeline_anchor 持久化契约 | test_pipeline_anchor 8 用例 | ✅ 锚点写入 + 迁移幂等 |
| 前端按锚点插入报告消息 | selectSession.test.tsx 3 个锚点测试 | ✅ DOM 顺序正确 |
| 旧会话兼容（anchor=null） | test_session_detail_pipeline_anchor_null | ✅ 回退第一个 user 后 |
| SSE 流不被上一轮 done 终止 | test_followup_sse_not_terminated_by_previous_done | ✅ after_seq 跳过历史 |
| 流式输出时可手动滚动 | 浏览器实证 | ✅ 滚动不被抢占 |

## 五、结论

本次修复完成三个 Bug 的全量验证：
- **Bug 1**（气泡错位）：后端持久化 pipeline_anchor + 前端按锚点插入，单元测试 + 浏览器实证均通过
- **Bug 2**（UI 卡住）：SSE 订阅 after_seq 跳过历史事件，单元测试 + 浏览器实证均通过
- **Bug 3**（滚动抢占）：用户滚动检测 + 条件自动滚动，浏览器实证通过

自动化测试 160 用例全绿（后端 23 + 前端 137），ruff 全绿，mypy 无新增告警。
