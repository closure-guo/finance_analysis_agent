## Context

### 现状

- **fire-and-forget**：`TradeDecision`（`models.py:55-68`）产出后渲染报告给用户即结束；`session_store` 只存会话内容（chat_history / timeline），不维护决策→结果回溯链。
- **零事后评估**：无 decision_log 表、无定时任务、无 forward return 计算、无决策效果 Score；全仓 grep `decision_log/pnl/actual_return` 零命中。
- **已有资产可复用**：AKShare 日 K 拉取（`fetch.py` 的 K 线逻辑）、Langfuse `score(trace_id=...)` 后置上报、SQLite（session_store 同库）、`langfuse_trace_id` 在生成时已可取（ADR-0015 的 trace 属性注入）。
- **互补 delta**：`agent-evaluation-suite` 的 `decision_grounding` 评"论据有无前文支撑"（逻辑一致性），本 delta 评"决策实际赚没赚钱"（事后效果）—— 一个 grounding 满分的决策仍可能亏钱，只有事后闭环能抓到。

### 约束

- **A 股做空受限**：`sell` 建议无法真实做空，只能评估"建议卖出/不买入"的方向准确性。
- **AKShare 数据时效**：日 K 仅收盘后可得，结算只能日批；停牌日无数据。
- **Langfuse trace 保留**：反向上报 Score 需 trace 在结算时仍可查（保留策略需确认，默认 Langfuse 长期保留）。
- **单 worker 部署**：定时任务可与 uvicorn 同进程（APScheduler in-process）或独立进程；首版选 in-process 简化部署。
- **TESTING=1**：stub 模式下 `TradeDecision` 为固定值，结算测试需用真实历史行情 fixture（不调 LLM，只测结算逻辑）。

## Goals / Non-Goals

**Goals:**

- 每个 `TradeDecision` 落 `decision_log`，事后可追溯到原 trace。
- 日批结算更新状态并反向上报 3 个 Score（hit / return / excess）。
- A 股主要异常（涨跌停 / 停牌 / sell 方向 / hold-watch）有明确定义的可执行结算规则。
- 基准对比（沪深 300）使"跑赢大盘"可度量。

**Non-Goals:**

- **不做实时盯盘结算** —— 日批（收盘后跑一次）即可，A 股日 K 粒度足够；实时分钟级结算留后续。
- **不做组合层面绩效** —— 本 delta 只评单决策方向 / 个股收益，不评组合 Sharpe / 回撤等（需组合记账，留后续）。
- **不做回测引擎** —— 不支持"对历史决策批量回放"，只对真实产生的决策做事后追踪；批量回测是另一议题。
- **不改业务决策逻辑** —— 决策仍由 Fund Manager 产出，本 delta 是旁路观测，不反馈进决策（不形成自动调参闭环）。
- **不选行业基准** —— 首版只沪深 300 宽基，申万行业基准留后续。
- **不处理复权细节的精确化** —— 首版用前复权日 K 近似，分红除权日的精确处理留 Open Question。

## Decisions

### 决策 1：存储复用 SQLite，新增 `decision_log` 表

**选择**：与 `session_store` 同库（SQLite），新增表：
```sql
CREATE TABLE decision_log (
  decision_id    TEXT PRIMARY KEY,
  session_id     TEXT NOT NULL,
  langfuse_trace_id TEXT,
  timestamp      TEXT NOT NULL,        -- ISO8601 决策时刻
  ticker         TEXT NOT NULL,
  name           TEXT,
  action         TEXT NOT NULL,        -- buy/sell/hold/watch
  entry_price    REAL NOT NULL,        -- 决策时现价
  stop_loss      REAL,
  target_price   REAL,
  confidence     REAL,
  position_size  REAL,
  status         TEXT NOT NULL DEFAULT 'open',  -- open/hit_stop/hit_target/expired
  settled_at     TEXT,
  settle_price   REAL,                 -- 实际结算价
  hold_days      INTEGER,
  decision_return REAL,                -- 实际收益率
  benchmark_return REAL,               -- 同期基准收益率
  decision_excess REAL,                -- 超额
  updated_at     TEXT NOT NULL
);
CREATE INDEX idx_decision_log_status ON decision_log(status);
```
**理由**：复用现有 SQLite 不引入新依赖；session_store 已有 migration 机制可扩展；单 worker 下同库读写无竞争。
**备选**：独立时序库（InfluxDB）—— 否决，单决策频率低（日均 < 100），SQLite 足够，过度工程。

### 决策 2：持仓周期——先到先结算 + 超期强制

**选择**：每日检查所有 `status=open` 决策，按优先级结算：
1. 期间最低价 ≤ stop_loss → `hit_stop`（止损触发）
2. 期间最高价 ≥ target_price → `hit_target`（目标达成）
3. 持仓天数 > `MAX_HOLD_DAYS`（默认 20 交易日，可配）→ `expired`（期末结算）
4. 三者都未触发 → 保持 `open`

止损 / 目标先到先结算（同日触及两个按止损优先，保守）；超期强制结算用结算日收盘价。
**理由**：先到先结符合交易直觉；超期避免 open 决策无限堆积；止损优先保守。
**备选**：固定 N 日结算（无视止损/目标）—— 否决，丢失止损/目标是否触发的关键信号。

### 决策 3：方向统一——`sell` / `hold` / `watch` 的 forward return 取负

**选择**：为统一"方向是否正确"，所有 action 的 `decision_return` 按方向符号化：
- `buy`：`decision_return = (settle_price - entry_price) / entry_price`（涨为正）
- `sell`：`decision_return = -(settle_price - entry_price) / entry_price`（sell 后跌为正）
- `hold` / `watch`：同 `sell` 语义（建议不买，后续跌为正）

`decision_hit` = `decision_return > 0`。
**理由**：A 股做空受限，`sell` 只能评估"建议卖出/不买入"的方向对错；符号化后 buy/sell/hold 可在同一把尺子下统计 hit rate。
**备选**：sell 单独定义"做空模拟收益" —— 否决，A 股无融券常态，模拟空收益脱离实际。

### 决策 4：A 股异常结算规则

**选择**：
- **涨跌停**：触及止损/目标但当日一字板（开盘即涨跌停且全天未打开）未成交 → 结算价用**次日首个可成交价**（次日开盘 / 涨跌停打开首日开盘），`decision_return` 按实际可成交价算；首版若次日仍一字板则递延至打开，记 `hold_days` 含等待日。首版**不**精确模拟部分成交，假设全额成交。
- **停牌**：停牌日无行情，不计入 `hold_days`，持仓周期顺延；结算价用复牌首日收盘。
- **复权**：用前复权日 K（AKShare 默认 `adjust="qfq"`），分红除权日的精确除权处理留 Open Question。
**理由**：涨跌停 / 停牌是 A 股常态，必须有规则；首版用可成交价近似比用涨跌停价（虚假）诚实。
**备选**：触及即按 stop_loss/target_price 记账（无视可成交性）—— 否决，一字跌停时实际亏损远大于 stop_loss，虚假记账误导。

### 决策 5：基准——沪深 300 宽基

**选择**：基准 = 沪深 300（000300）同期收益率，`benchmark_return = (基准结算价 - 基准决策时价) / 基准决策时价`，`decision_excess = decision_return - benchmark_return`（注意：excess 对 sell/hold 方向同理符号化，即基准也取负后再比）。
**理由**：宽基最简单、最可比；行业基准（申万）需匹配股票所属行业，复杂度高，留后续。
**备选**：申万行业指数 —— 否决，首版过重。

### 决策 6：定时任务——APScheduler in-process，收盘后日批

**选择**：APScheduler in-process（与 uvicorn 同进程，单 worker 下无竞争），每个交易日 16:00（收盘后）触发一次结算 job，遍历 `status=open` 决策。失败重试 3 次（指数退避），job 幂等（重复执行不重复上报 Score，以 `settled_at IS NULL` 为准）。
**理由**：单 worker 部署下 in-process 最简；AGENTS.md 已约束不可 `--workers N`，无多进程竞争。
**备选**：独立 celery worker —— 否决，引入 broker 依赖，过度工程；cron + 独立脚本 —— 否决，部署割裂。
**注**：定时任务框架选型属架构决策，**建议人工落 ADR** 确认（agent 不自建 ADR）。

### 决策 7：Score 反向上报——按 `langfuse_trace_id` 后置

**选择**：结算后调 `langfuse.score(trace_id=decision.langfuse_trace_id, name=..., value=..., data_type=...)` 反向上报 3 个 Score（hit / return / excess），附 `comment` 含结算价 / 持有期 / 基准。trace 不存在或已过期时记 WARN 不阻断。
**理由**：Langfuse SDK 支持按 trace_id 后置 score；使"决策→trace→效果"在 UI 可联查。
**备选**：只存表不报 Langfuse —— 否决，失去与 trace 的联动，无法在 Dashboard 看效果分布。

## Risks / Trade-offs

- **[A 股结算复杂度]** → 首版用保守近似（决策 4），Open Question 记录精确化诉求；结算逻辑全部纯函数 + 历史 fixture 测试，不依赖 LLM。
- **[定时任务是新运行组件]** → 幂等 + 失败重试；job 失败不阻断业务（旁路）；监控 job 执行（日志 + open 决策堆积告警）。
- **[Langfuse trace 保留期]** → 反向上报需 trace 可查；保留策略需与运维确认，过期 trace 的 Score 上报记 WARN。
- **[AKShare 行情缺失/延迟]** → 某标的当日无数据时该决策跳过本次结算，下次重试；连续 N 日无数据标 `data_stale` 告警。
- **[decision_excess 对 sell 方向的语义]** → 决策 5 的符号化需文档说明，避免"sell 且跑赢基准"被误读。
- **[MAX_HOLD_DAYS 取值]** → 20 交易日为默认，不同策略周期不同，配置化暴露；首版固定默认值。

## Migration Plan

- 无业务数据迁移；新增 `decision_log` 表经 SQLite migration 创建，首次启动自动建表。
- 历史已产生的 `TradeDecision`（存于 session_store 的 timeline）**不回溯补录** —— 本 delta 只对实施后新产生的决策追踪；回溯补录需从 timeline 反解，价值有限，Non-Goal。
- 回滚：删除表 + 关闭定时任务 + 移除 Score 上报，业务无影响（纯旁路）。

## Open Questions

- 涨跌停一字板的精确成交模拟（部分成交、滑点）—— 首版全额近似，是否需精细化待 bad case 驱动。
- 复权处理 —— 前复权首版够用，分红除权日的精确除权需 AKShare 复权因子核对。
- 是否对 `confidence` 高的决策单独统计 hit rate（验证模型自评准确性）—— 留后续分析。
- 定时任务框架（APScheduler vs cron）—— 建议人工 ADR 确认。
- 是否需要"决策效果 → 反馈进 prompt 迭代"的自动闭环 —— 显式 Non-Goal，本 delta 不形成自动调参。
