# 问题与事件记录

本目录记录项目中发现的**系统性问题**、根因分析和修复方案。

> **边界说明**：本目录是系统性问题的复盘（为什么会出问题、如何防止再发），供团队长期参考避坑。
> 单次变更的 archive 验收证据（测试是否通过、行为是否符合预期）请落 `tests/validation/`。
> 一个 bug 若既是系统性问题又需验证报告，两边都放，incident 引用 validation，不重复内容。

| 编号 | 日期       | 标题                                                                | 状态     |
| ---- | ---------- | ------------------------------------------------------------------- | -------- |
| 001  | 2026-06-01 | [LLM 幻觉：数据正确但输出失真](001-llm-hallucination-20260601.md)   | 已修复   |
| 002  | 2026-05-26 | [报告准确性复盘：茅台 FA 分析偏差](002-report-accuracy-20260526.md) | 部分修复 |
| 003  | 2026-06-03 | [股票名称获取失败 + NaN 处理缺陷](003-stock-name-and-na-handling-20260603.md) | 已修复   |
| 004  | 2026-06-04 | [数据准确性系统性问题 — efficiency 年份错位 + ROE 口径 + LLM 自算](004-data-accuracy-20260604.md) | 已修复 |
| 005  | 2026-06-04 | [GARP 格式化 bug + 杜邦口径混淆 + 测试污染](005-garp-dupont-test-pollution-20260604.md) | 已修复 |
| 006  | 2026-07-16 | [深度模式无响应 - citation 重试无限循环](006-citation-infinite-loop-20260716.md) | 已修复 |
| 007  | 2026-07-16 | [侧边栏会话时间显示 "Invalid Date"](007-sidebar-invalid-date-20260716.md) | 已修复 |
| 008  | 2026-07-16 | [深度分析交互卡顿 - AKShare 数据拉取失败无重试](008-deep-analysis-stuck-akshare-20260716.md) | 部分修复 |
| 009  | 2026-07-17 | ["热门股票"类时效性查询被错误路由进深度分析管线](009-hot-stock-query-routing-20260717.md) | 已修复 |
| 010  | 2026-07-23 | [测试全过但前端交互 bug 频出 - 缺少行为 spec 约束](010-frontend-interaction-bugs-missing-spec-20260723.md) | 处理中 |
| 011  | 2026-06-04 | [AKShare 预计算字段缺失 - 应收账款周转率返回 NaN](011-akshare-ar-turnover-nan-20260604.md) | 已修复 |
| 012  | 2026-07-27 | [SSE 流式测试 deselect（技术债追踪）](012-sse-stream-tests-deselected-20260727.md) | 追踪中 |
| 013  | 2026-08-04 | [流式输出概率性文字错乱 — 三轮静态推理失败 + 并发写 DB 数据丢失](013-sse-concurrent-text-corruption-20260804.md) | 已修复 |
| 014  | 2026-07-16 | [刷新页面导致历史会话清空 — 事件循环被高频同步 SQLite 写冻结](014-refresh-clears-session-list-20260716.md) | 已修复 |
| 015  | 2026-08-05 | [E2E timeline suite report_ready 丢失 — REPORTS_DIR 递归创建缺失](015-reports-dir-mkdir-parents.md) | 已修复 |
| 016  | 2026-08-16 | [litellm 流式 logging 线程在 Windows socketpair 竞态死锁 — 跑批挂死](016-litellm-stream-logging-deadlock.md) | 已修复 |
| 017  | 2026-08-16 | [方舟 GLM-5.2 reasoning 吃满 max_tokens 配额 — 截断/空输出炸行](017-ark-glm-reasoning-token-starvation.md) | 已修复 |
| 018  | 2026-08-17 | [LLM Provider 迁移连环兼容性故障 - 7 bug 全景与 Gateway 根治重构](018-llm-provider-migration-gateway-refactor.md) | 已修复(表层)/重构落地 |
| 019  | 2026-08-24 | [LLM 输出截断治理 — 静默截断、重试空转与 reasoning 配额吃空](019-llm-output-truncation-governance.md) | 阶段修复 |
| 020  | 2026-08-28 | [citation 校验器契约疾病 — 索引错位、词表分裂与容差失真制造大面积假 FAIL](020-citation-contract-diseases-20260828.md) | 已修复(待合并) |
| 021  | 2026-08-25 | [深研管线「假卡死」— 事件落库限速终态迟到 + 管线超时空转](021-deep-analysis-session-stuck.md) | 已修复 |
| 022  | 2026-08-30 | [契约修复冒烟验证 — 第四类契约疾病浮现（技术上下文数组方向未声明）](022-citation-smoke-verify-20260830.md) | 部分修复 |

---

## 按主题分类

### LLM 输出可靠性

- [001](001-llm-hallucination-20260601.md) LLM 编造财务数字、行业PE无源、PE口径混淆
- [019](019-llm-output-truncation-governance.md) 静默截断/重试空转/reasoning 配额吃空 → 续写 + 预算对齐官方治理

### 引用校验（citation）

- [006](006-citation-infinite-loop-20260716.md) 深度模式无响应 - citation 重试无限循环
- [020](020-citation-contract-diseases-20260828.md) 考卷与答案册不同源：context 裁剪索引/中文词表/绝对容差 → 61% 假 FAIL；负索引约定 + 单一词表 + 相对容差，离线重判 41→5（残量全为真幻觉）
- [022](022-citation-smoke-verify-20260830.md) 修复后多标的冒烟：稳态标的 2.2% FAIL 清零成疾；异动股暴露第四类契约疾病（技术 context 数组方向未声明 → LLM 期次错位，校验器裁决正确）

### 评分与分析模型

- [002](002-report-accuracy-20260526.md) 指标体系不适合白酒行业、归因逻辑错误、评分模型缺陷
- [003](003-stock-name-and-na-handling-20260603.md) 行业阈值覆盖、NaN 处理缺陷、数据降级链路

### 数据质量

- [004](004-data-accuracy-20260604.md) efficiency.py 年份错位 bug、ROE 口径差异、LLM 自算未提供指标
- [011](011-akshare-ar-turnover-nan-20260604.md) AKShare 预计算字段缺失（应收账款周转率 NaN），降级为自算
- ADR-0005 `docs/adr/0005-validate-financials.md` 勾稽校验（4条规则）

### 测试体系与开发流程

- [010](010-frontend-interaction-bugs-missing-spec-20260723.md) 测试从实现反推、e2e 形同虚设、缺少行为 spec 约束 → 引入 OpenSpec + Superpowers SDD 体系
- [013](013-sse-concurrent-text-corruption-20260804.md) 并发 bug 用静态推理修不好（必须 E2E 复现 + 运行时证据）；测试/生产共用 SQLite 导致数据不可恢复 → 补并发 E2E + DB 环境变量隔离
