# Design: expose-decision-outcomes

## Context

`decision-outcome-tracking`（进行中提案）已建立 `decision_log` 表（与 session_store 同库 SQLite，WAL）、日批结算 job 与 Langfuse Score 回传。表结构含展示所需的全部字段（见 `src/finance_agent/outcome/store.py` 的 DECISION_LOG_DDL）。当前缺口纯在「读路径」：api.py 无任何 decision 查询端点，前端无对应页面。

前端已有可复用模式：下载中心（`frontend/src/pages/downloads/DownloadCenter.tsx`）证明了「侧边栏入口 → pathname 条件渲染独立页 → 只读列表 API → 空态/刷新」这一页面形态；`/api/files`（api.py:2068）是只读列表端点的范本。

## Goals / Non-Goals

**Goals:**
- 两个只读端点 + 一个战绩页面，把已有结算数据暴露给用户
- 零写入路径、零 schema 变更，对现有结算/落库逻辑零侵入

**Non-Goals:**
- 不改结算规则、不改落库挂点、不改 Langfuse 回传
- 不做自选股、告警推送、组合分析（后续独立提案）
- 不做鉴权（项目定位单用户本地部署）
- 不做决策的人工标注/修正入口（只读）

## Decisions

**决策 1：查询函数落在 `outcome/store.py`，与写路径同模块。**
新增 `list_decisions(ticker, status, db_path)` 与 `decision_stats(db_path)` 两个只读函数，复用现有 `_connect` 短连接模式。备选方案是端点内直接写 SQL——拒绝，store.py 已是 decision_log 的唯一访问收口，端点直写 SQL 会制造第二个真相源。

**决策 2：聚合在 SQL 层做，不在 Python 层逐行汇总。**
数据量虽小，但 `COUNT + AVG(CASE WHEN ...)` 一次查询完成，语义（null 剔除、open 不计入）在 SQL 里显式表达，比在 Python 里循环更不易错。胜率分母 = 已结算记录数；`decision_excess` 均值用 `AVG(decision_excess)`（SQLite AVG 天然跳过 NULL）。

**决策 3：列表端点首版不做分页，做上限。**
决策产生速率是「每次分析最多 1 条」，单用户本地使用一年量级数百条。端点支持 `limit`（默认 200，上限 1000）+ 倒序即可，不引入 cursor/offset 分页复杂度。备选「完整分页」在数据量增长到万级前是过度设计。

**决策 4：前端复用下载中心页面模式，不进会话视图。**
独立 pathname（`/decisions`）+ 侧边栏入口（折叠/展开两态都要入口，参照 sidebar.tsx 现有 downloads 实现）。放进会话视图内嵌 Tab 是备选——拒绝，因为战绩是跨会话的全局视角，与会话生命周期无关。

**决策 5：跳转来源会话复用现有会话加载路径。**
决策行携带 `session_id`，点击后导航到 `/` 并选中该会话（与 `restore-session-on-refresh` 的会话恢复机制同路）。会话不存在时后端 `/api/sessions/{id}` 返回 404，前端 toast 提示，不新建会话。

## Risks / Trade-offs

- [decision-outcome-tracking 未归档，主规范库尚无 decision-outcome capability] → 本 delta 全部为 ADDED Requirements，sync 时按并行变更规则追加合并；若 tracking 先归档则无冲突，若本提案先 sync 则 capability 由两份 delta 共同构成，archive 顺序在合并时人工确认。
- [已结算样本极少时（如 1 条）胜率/均值误导性解读] → 汇总卡同时展示已结算计数，小样本一目了然；不做置信区间等统计修饰（产品层非评估层）。
- [action 为 hold/watch 的收益符号化口径用户不易理解] → 列表 tooltip 注明「卖出/观望类建议的收益为方向符号化结果（下跌为正）」，与 settle.py `_direction_sign` 口径一致。

## Migration Plan

纯新增读路径：部署即生效，无需迁移。回滚 = 移除端点与页面入口，`decision_log` 数据不受影响。

## Open Questions

- 汇总卡是否需要「按 action 分组」的分层战绩（buy 与 sell/hold/watch 分开统计）？首版不做，等真实数据积累后在后续迭代评估。
