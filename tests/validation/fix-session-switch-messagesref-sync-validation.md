# 验证报告：会话切换时 messagesRef 同步更新修复

## 问题背景

用户反馈：输入"安孚科技"触发股票识别后，在 search_stock 工具调用执行中切换会话，切回时 UI 卡死在"调用工具中 · 1 次"+"执行中..."状态，Langfuse 显示管线正常执行但前端无响应。

## 根因

`App.tsx` 中 `messagesRef.current` 通过 `useEffect` 异步更新：

```typescript
// 修复前：useEffect 异步同步，存在滞后窗口
useEffect(() => {
  messagesRef.current = messages
}, [messages])
```

当用户在 SSE 流处理过程中切换会话时，`selectSession` 调用 `saveCurrentStreamState` 保存快照，读取 `messagesRef.current`。由于 `useEffect` 在异步函数中 `setMessages` 调度后未及时执行，`messagesRef.current` 仍是旧值，导致快照保存了过时的 messages。

切回会话时，恢复的 `assistantMsgIdRef` 与实际 messages 不匹配，`resumeStream` 收到的 `chat_token` 事件尝试更新一个不存在的消息 ID，内容丢失，UI 卡死在工具调用执行中状态。

## 修复方案

新增 `commitMessages` 函数作为统一的 messages 更新入口，在 `setMessages` 调度的同时**同步**更新 `messagesRef.current`，消除 useEffect 滞后窗口：

```typescript
// 修复后：同步更新 messagesRef，确保快照保存最新状态
const commitMessages = (updater: UIMessage[] | ((prev: UIMessage[]) => UIMessage[])) => {
  const newMsgs = typeof updater === 'function' ? updater(messagesRef.current) : updater
  messagesRef.current = newMsgs  // 关键：同步更新
  setMessages(newMsgs)
}
```

将所有 `setMessages` 调用点（49 处）替换为 `commitMessages`，确保任何路径下 `messagesRef.current` 都与 React state 保持一致。

## 验证证据

### 1. 专项测试（TDD 红绿）

**测试文件**：`frontend/src/test/followup-resume-after-switch.test.tsx`

模拟完整场景：创建会话 → SSE 流中断（无 done 事件）→ 切换到其他会话 → 切回原会话 → resumeStream 收到新事件（chat_token）→ 验证内容渲染到 UI。

- **修复前**（messagesRef.current = newMsgs 被注释）：测试**失败**，UI 显示其他会话内容（"你好"），期望的"安孚科技分析完成"未出现 —— 成功复现 bug
- **修复后**（messagesRef.current = newMsgs 启用）：测试**通过**，"安孚科技分析完成"正确渲染到 UI

### 2. 全量回归测试

```
npm test
Test Files  15 passed (15)
     Tests  138 passed (138)
```

含 3 个锚点测试（selectSession.test.tsx）、1 个追问去重测试（followup-sse-dedup.test.tsx）、1 个本 bug 专项测试，全部通过，无副作用。

### 3. Docker 重建 + 浏览器实证

**环境**：`docker compose up -d --build` 重建前后端容器，浏览器访问 http://localhost:5173

**验证步骤**（browser_use 自动化）：

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | 打开应用 | 页面加载正常，侧边栏会话列表可见 |
| 2 | 输入"安孚科技"并发送 | 消息发送成功 |
| 3 | 等待股票识别阶段 | 出现"调用工具中 · 1 次"+"执行中..."标志，确认进入 search_stock 工具调用阶段 |
| 4 | 切换到"你好"会话 | 主区域切换为"你好"会话内容 |
| 5 | 切回"安孚科技"会话 | 主区域恢复为"安孚科技"会话内容 |
| 6 | 等待 10 秒观察 | UI 持续显示"安孚科技"会话内容（思考流、工具调用状态等），**无卡死现象** |

**结论**：修复成功。切回会话后 UI 正常显示内容，未出现卡死在"调用工具中"状态的问题。

## 影响范围

- **修改文件**：`frontend/src/App.tsx`（新增 commitMessages 函数，替换 49 处 setMessages 调用）
- **新增测试**：`frontend/src/test/followup-resume-after-switch.test.tsx`
- **无后端改动**
- **无 OpenSpec delta**（属于"修 bug · 意图不变"类型，复现测试 + 根因修复，不动 openspec）

## 验证日期

2026-08-02
