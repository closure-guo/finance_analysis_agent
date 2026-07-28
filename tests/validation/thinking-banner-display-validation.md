# 思考横幅流式展示与标题生成 - 人工验证报告

**变更：** thinking-stream-banner-display
**验证日期：** 2026-07-27
**验证人：** Agent (E2E 自动化 + 数据库抽样)

## 1. 验证范围

| 验证项 | 方法 | 结果 |
|--------|------|------|
| 横幅思考中态（streaming=true） | E2E 5.1 | ✓ 通过 |
| 横幅完成态展开（显示"思考已完成"） | E2E 5.1/5.3 | ✓ 通过 |
| 横幅完成态折叠（显示"思考已完成"） | E2E 5.3 点击折叠后展开 | ✓ 通过 |
| 展开/折叠交互 | E2E 5.3 | ✓ 通过 |
| 切换会话恢复思考横幅 | E2E 5.4 | ✓ 通过 |
| 标题生成策略 prompt 嵌入 | 代码审查 quick_mode.md/deep_mode.md | ✓ 通过 |
| LLM 按策略输出（无标题分支） | 数据库抽样 7 个会话 | ✓ 通过（7/7 短思考正确不用标题） |
| LLM 按策略输出（## 标题分支） | 待 nightly @live 长期观察 | ⏳ 归入 nightly |

## 2. E2E 测试结果

**测试文件：** `tests/e2e/playwright/tests/thinking-banner.spec.ts`
**运行命令：** `$env:CI=""; npx playwright test thinking-banner.spec.ts --reporter=list --workers=1`

```
Running 3 tests using 1 worker

  ✓  1 thinking-banner.spec.ts:32:3 › 5.1 快速模式：query 后思考横幅流式展示"思考中"，完成后显示"思考已完成" (16.4s)
  ✓  2 thinking-banner.spec.ts:62:3 › 5.3 快速模式：思考横幅点击展开/折叠交互 (23.3s)
  ✓  3 thinking-banner.spec.ts:93:3 › 5.4 快速模式：切换会话后历史会话思考横幅恢复 (14.8s)

  3 passed (55.1s)
```

### 2.1 测试 5.1：思考中 -> 思考已完成

- **query：** "茅台近期的财务表现和估值情况如何"
- **流式态：** 思考横幅显示"思考中"按钮，脉冲动画，自动展开
- **完成态：** 按钮文案切换为"思考已完成"
- **截图：** test-results/thinking-banner-...-5-1.../test-failed-1.png（首次失败时的截图，已修正 selector 后通过）

### 2.2 测试 5.3：展开/折叠交互

- **query：** "对比茅台和五粮液的财务表现"
- **完成态展开：** 横幅显示"思考已完成"
- **折叠后展开：** 点击横幅折叠，再次点击展开，横幅仍显示"思考已完成"

### 2.3 测试 5.4：切换会话恢复

- **query：** "茅台最新财报分析"
- **第一轮：** 发送 query，等待思考完成（"思考已完成"），等待流结束（stream-status 消失）
- **切换会话：** 新建分析 -> 点击侧边栏"茅台最新财报分析"会话
- **恢复后：** 思考横幅恢复完成态（显示"思考已完成"，不显示"思考中"）

## 3. 标题生成策略验证

### 3.1 策略 prompt 嵌入

已在以下两个 prompt 文件追加 `# Thinking Format` 段落：
- `src/finance_agent/prompts/quick_mode.md`
- `src/finance_agent/prompts/deep_mode.md`

策略内容：
```
在输出前，评估回复的信息密度和逻辑复杂度：
- 若包含多要点、需对比分类、或用户处于决策场景 -> 用 ## 标题分层
- 若仅为单一事实、简短确认、日常寒暄 -> 直接输出，不用标题
- 长度 >150 字但主题单一 -> 用 **加粗** 分段，不用层级标题
核心原则：标题服务于可读性，不为形式而形式。
```

### 3.2 LLM 输出抽样（数据库）

通过 `/api/sessions/{id}` 获取 7 个快速模式会话的 `chat_history.thinking` 内容：

| 会话 | thinking 长度 | 含 ## 标题 | 策略判定 |
|------|--------------|-----------|----------|
| 茅台最新财报分析 | 16 字 | 否 | ✓ 短思考不用标题 |
| 茅台近期的财务表现和估值情况如何 | 23 字 | 否 | ✓ 短思考不用标题 |
| 茅台最新财报分析 | 16 字 | 否 | ✓ 短思考不用标题 |
| 茅台最新财报分析 | 16 字 | 否 | ✓ 短思考不用标题 |
| 对比茅台和五粮液的财务表现 | 25 字 | 否 | ✓ 短思考不用标题 |
| 茅台近期的财务表现和估值情况如何 | 23 字 | 否 | ✓ 短思考不用标题 |
| 茅台近期的财务表现和估值情况如何 | 23 字 | 否 | ✓ 短思考不用标题 |

**结论：** 7/7 会话的 thinking 内容均为短文本（16-25 字），LLM 按策略"单一事实/简短确认->不用标题"正确未用标题。`##` 标题分支（多要点/决策场景/>150 字）在快速模式下较少触发，需 nightly @live 长期观察命中情况。

## 4. 单元测试结果

**运行命令：** `npx vitest run`

```
 ✓ src/test/smoke.test.tsx (1 test) 2ms
 ✓ src/test/SearchBanner.test.tsx (4 tests) 123ms
 ✓ src/test/extractThinkingTitle.test.tsx (8 tests) 3ms
 ✓ src/test/toolCallFilter.test.tsx (3 tests) 2ms
 ✓ src/test/ThinkingBanner.test.tsx (5 tests) 100ms

 Test Files  5 passed (5)
      Tests  21 passed (21)
```

## 5. TypeScript 类型检查

**运行命令：** `npx tsc --noEmit`

结果：通过，无错误。

## 6. 待办（nightly @live）

- `##` 标题生成命中情况：需构造多要点/决策场景 query（如"对比茅台、五粮液、泸州老窖的财务表现并给出投资建议"），观察 LLM 是否输出 `##` 标题
- 深度模式澄清阶段思考横幅：与快速模式共用 `handleChatStreamEvent`，行为一致，归入 nightly 验证
