# 问题与事件记录

本目录记录项目中发现的系统性问题、根因分析和修复方案。

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

---

## 按主题分类

### LLM 输出可靠性

- [001](001-llm-hallucination-20260601.md) LLM 编造财务数字、行业PE无源、PE口径混淆

### 评分与分析模型

- [002](002-report-accuracy-20260526.md) 指标体系不适合白酒行业、归因逻辑错误、评分模型缺陷
- [003](003-stock-name-and-na-handling-20260603.md) 行业阈值覆盖、NaN 处理缺陷、数据降级链路

### 数据质量

- [004](004-data-accuracy-20260604.md) efficiency.py 年份错位 bug、ROE 口径差异、LLM 自算未提供指标
- [011](011-akshare-ar-turnover-nan-20260604.md) AKShare 预计算字段缺失（应收账款周转率 NaN），降级为自算
- ADR-0005 `docs/adr/0005-validate-financials.md` 勾稽校验（4条规则）

### 测试体系与开发流程

- [010](010-frontend-interaction-bugs-missing-spec-20260723.md) 测试从实现反推、e2e 形同虚设、缺少行为 spec 约束 → 引入 OpenSpec + Superpowers SDD 体系
