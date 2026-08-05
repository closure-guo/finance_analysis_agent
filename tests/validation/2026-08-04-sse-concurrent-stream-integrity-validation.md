# 人工验证报告：SSE 并发流式文字错乱修复

**日期**: 2026-08-04
**验证人**: [agent]
**关联 incident**: [docs/incidents/013-sse-concurrent-text-corruption-20260804.md](../../docs/incidents/013-sse-concurrent-text-corruption-20260804.md)
**关联代码**: `frontend/src/App.tsx:947`、`frontend/src/App.tsx:2242`

## 验证范围

流式输出概率性文字错乱 bug 的根因修复。根因：`session_created` 事件处理处只更新 React state，`currentSessionIdRef` 等 useEffect 异步同步，窗口内到达的 `chat_token` 被会话隔离检查误判丢弃。

## 验证方式

**E2E 复现 + 固定 stub 文本精确断言**。后端 `TESTING=1` 启用 StubLLMClient，吐固定已知文本（`"这是一段测试用的固定回复。用于验证流式渲染的增量累积。"`），前端按字符级断言完整性——可精确判断"该出现的没出现"，而非模糊"内容有增长"。

## E2E 门禁验证结果

| Scenario | 预期行为 | 实际结果 | 通过 |
|----------|----------|----------|------|
| 两会话并发 + 同标签切换 | 切换后两会话内容均完整渲染 | 8/8 通过（重复 4 轮 × 2 用例） | ✅ |
| 纯并发（不切换） | 两会话各自完整渲染 | 内容完整，无交叉无丢失 | ✅ |

- 测试文件：`tests/e2e/playwright/tests/concurrent-streaming-integrity.spec.ts`
- 运行命令：`npx playwright test concurrent-streaming-integrity.spec.ts --config=playwright.isolated.config.ts`
- 结果：8 passed (0 failed)

## 单元测试验证结果

| 文件 | 用例数 | 预期 | 实际 | 通过 |
|------|--------|------|------|------|
| `frontend/src/test/session-created-ref-sync.test.ts` | 6 | 根因回归 | 6/6 | ✅ |
| 全套 vitest | 183 | 零回归 | 183/183 | ✅ |
| 后端 pytest | 619 | 零回归 | 619/619 | ✅ |

## 根因证据（SSE 轨迹）

`?sse_debug` 诊断开关输出（修复前）：

```
chat_token seq=5 "这是"      ✓ 渲染
chat_token seq=6 "一段"      ✓
chat_token seq=7 "测试用的"   ✓
chat_token seq=8 "固定回复。"  ✓
← seq 9/10/11 无任何日志，静默消失
```

修复后 seq 5→11 全部渲染，前端文本与后端 `chat_history` 完全一致。

## 连带修复（DB 并发写）

| 改动 | 验证 |
|------|------|
| `session_store.py` 支持 `SESSIONS_DB_PATH` | E2E 跑完后生产库 `integrity: ok` 且 `LastWrite` 未被触碰 |
| 4 个 playwright 配置注入独立测试库 | `test-e2e-sessions.db` 独立生成，与生产库物理隔离 |

## 结论

- [x] 全部通过，可视为修复有效
- [ ] 存在失败项，需修复后重新验证

根因修复经 E2E 8/8 稳定验证，连带 DB 隔离修复经生产库完整性验证。前三轮次要路径修复（`resumeAfterSeqFromSnapshot` / `streamingSessionIdRef` 局部化 / `ensureSingleReader`）均保留，共同构成完整防线。
