# 014: 刷新页面导致历史会话清空 — 事件循环被高频同步 SQLite 写冻结

**日期**: 2026-07-16
**状态**: 已修复（核心根因已解决，用户实测确认「不再清空」）
**严重级别**: 高（用户数据「看似丢失」，实际未丢，但严重影响信任与可用性）
**影响范围**: 股票分析管线运行期间刷新页面 → 左侧会话历史列表空白
**现象**: 管线（含 ReAct 澄清/深度分析）运行中刷新页面，侧边栏「会话历史」完全空白；分析结束后刷新正常。

> 本文原归档于 `tests/validation/incident-refresh-clears-session-list.md`，因其为系统性根因分析（非单次变更验收证据），按目录边界规范迁移至此。

---

## 1. 结论速览

> **数据从未丢失**（SQLite 中 chat_history / pipeline_snapshot / journal 完整）。
> 根因是**后端事件循环被高频同步 SQLite 写冻结**，导致 `/api/sessions` 超时；
> 叠加**前端刷新不持久化当前会话 + 拉取失败即清空列表**两个设计缺陷，
> 最终表现为「一刷新历史会话全空」。

## 2. 根因（三层叠加）

### 2.1 直接根因：事件循环被高频同步 SQLite 写冻结（最终实锤）

后端 FastAPI 单线程 async 事件循环。管线运行流式产生**数百个 thinking chunk**
（4 分析师 + 辩论 + Trader + 风控，各自流式思考）。

`agent_factory.py` 的 `_background_consume` 是 `async` 协程，**跑在事件循环线程上**，
却对**每个 thinking chunk 同步调用 `session_store.update_pipeline_timelines`**
（`open → execute → commit → close` 完整 SQLite 写事务），**未走 `asyncio.to_thread`**。

py-spy 实锤事件循环线程堆栈：

```
Thread MainThread (事件循环)
  update_pipeline_timelines (session_store.py:698)   ← 同步 SQLite 写
  _background_consume (agent_factory.py:428)          ← 事件循环线程上直接调用
  asyncio/runners.py
```

高频同步写（每 chunk 一次）+ SQLite WAL 锁等待 → **事件循环被占满/冻结**：

- `GET /api/sessions`（前端拉会话列表）→ 超时挂起
- `GET /api/health`（Docker 健康检查）→ 超时（容器 unhealthy）

前端 `loadSessions` 拿不到响应 → 早期版本失败即降级为空列表 → **侧边栏空白**。

**修复**：`_background_consume` 内所有同步 session_store 写改 `await asyncio.to_thread`
移出事件循环，并对 thinking chunk 写加 0.5s 节流（31 次写 → 3 次）。
回归测试：`tests/test_pipeline_write_blocking.py`（复现前 31 次写冻结事件循环、探针仅 2 次；
修复后 3 次写、事件循环保持响应）。

### 2.2 叠加的历史包袱（前几轮逐个排掉的阻塞源）

事件循环之所以易被压垮，是多个阻塞源叠加，前几次修复逐一排除：

| 阻塞源 | 说明 | 修复 |
|--------|------|------|
| 同步 SQLite 读 | `/api/sessions` 等同步查询也在事件循环跑 | api.py 15 处改 `to_thread` |
| `_call_ak` 线程泄漏 | AKShare 同步调用泄漏线程打满默认 executor 池（仅 20 线程） | `shutdown(wait=False, cancel_futures=True)` |
| ReAct `_run_graph` 抢默认池 | matplotlib `findfont` 全盘字体扫描占满默认池 | 独立 `_pipeline_executor`（thread_name_prefix="pipeline"）隔离 |

> 教训：本类「事件循环冻结」问题前几次都修在外围（读 to_thread、线程池隔离），
> 未触及核心（事件循环上的高频同步写），导致反复复发。**最终靠 py-spy 抓真实堆栈才定位**。

### 2.3 放大问题的设计缺陷

1. **前端无自动恢复**：刷新后 `currentSessionId` 为纯内存、未持久化，刷新即丢 →
   回空态首页，加剧「会话没了」观感（实为视图丢失，非数据丢失）。
   → delta `restore-session-on-refresh`：`localStorage` 持久化 + mount 自动恢复。
2. **前端 `loadSessions` 早期为有限重试 + 失败即置空**：后端一抖就清空列表。
   → 改无限重试 + 失败保留旧值，仅明确 200 空才清。

## 3. 关键证据

- py-spy 事件循环线程堆栈（见 §2.1）。
- 修复前 `Invoke-WebRequest /api/health`、`/api/sessions` 超时；后端容器 `unhealthy`。
- 修复后 `/api/health`、`/api/sessions` 均 200，后端 `healthy`；用户实测刷新不再清空。

## 4. 修复清单

| 层 | 改动 | 文件 |
|----|------|------|
| 后端 | `_background_consume` 同步写改 `to_thread` + thinking 写节流 + 结束 flush | `src/finance_agent/agent_factory.py` |
| 后端 | API 同步 SQLite 读改 `to_thread`（15 处） | `src/finance_agent/api.py` |
| 后端 | `_call_ak` 线程泄漏修复 | `src/finance_agent/`（AKShare 调用处） |
| 后端 | ReAct `_run_graph` 独立 `_pipeline_executor` | `src/finance_agent/agent_factory.py` |
| 前端 | `loadSessions` 无限重试 + 失败保留旧值 | `frontend/src/App.tsx` |
| 前端 | 刷新自动恢复当前会话（localStorage 持久化） | `frontend/src/App.tsx`（delta `restore-session-on-refresh`） |

## 5. 回归测试

- `tests/test_pipeline_write_blocking.py` — 事件循环不被高频同步写冻结（本 incident 核心）。
- `tests/test_api_event_loop_blocking.py` — API 读不阻塞事件循环。
- `tests/test_react_executor_isolation.py` — ReAct 管线线程池隔离。

## 6. 后续预防

- 事件循环线程上**禁止任何同步 SQLite / 阻塞 IO**，统一 `asyncio.to_thread`。
- 高频写（流式 chunk 级）必须**节流**，避免写放大。
- 前端关键 UI 状态（当前会话）应**持久化**，刷新可恢复。
- 列表拉取失败**不清空已有数据**，仅明确空结果才清。
