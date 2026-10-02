# Design: add-index-performance-compare

## Context

历史战绩(track-record)页当前仅有「组合净值 vs 沪深300」双线图:盯市日批(`daily_marking`)把 000300 收盘写进 `daily_marks.benchmark_price` → 指标引擎产出 `equity_curve.benchmark_nav` → `GET /api/v1/track-record/equity-curve` 返回单条基准序列。指数取数已泛化(`AKShareClient.fetch_index_kline(index_code)`,东财→新浪回退),但存储层只有 000300 一条。`fetch_index_kline` 无复权概念,指数收盘天然可回填历史。净值曲线 2026-09-28 起步,窗口内对比以 equity_curve 实际覆盖区间为准。

## Goals / Non-Goals

**Goals:**
- 新增多指数收盘存储 `index_closes`(幂等 upsert,可回填),由盯市日批顺带维护
- 新增 `index-compare` API:按时间跨度返回组合与各指数的区间累计收益 + 跑赢/跑输
- 战绩页新增「跑赢指数对比」卡片,时间跨度复用 `fa_track_prefs.timeSpan`(切换跨度时与净值图联动)

**Non-Goals:**
- 不改 win/loss 判定基准(仍沪深300,`metrics.md` 预登记口径)
- 不改 `equity_curve` 表结构与 equity-curve 端点输出(旧字段原样)
- 不做净值图多基准叠加(上一轮讨论的多选叠加,留待后续变更,基础设施就绪后成本很低)
- 不做指数集合的用户自定义(settings-center 不动)

## Decisions

1. **独立新表 `index_closes` 而非在 `daily_marks` 加列**:指数收盘与「观点盯市」是两个聚合根;加列会随指数集扩张改 schema,新表天然支持任意指数集。`(index_code, trade_date)` 主键,`INSERT OR REPLACE` 幂等。
2. **指数集为代码级常量 `INDEX_COMPARE_UNIVERSE`**:起始集 {000001 上证指数, 000300 沪深300, 000905 中证500, 000852 中证1000, 399006 创业板指},新指数只改常量+回填,不做配置化(Non-Goal)。
3. **日批挂 `daily_marking` 顺带拉取而非独立 job**:指数收盘与盯市同频(工作日收盘后),无需单独调度行;单指数失败 catch 后仅记 WARNING,不进 marking 汇总 errors(避免把展示层数据缺失放大成盯市失败),失败次日自然补齐(幂等 upsert)。
4. **历史回填为一次性脚本 + API 侧缺数兜底**:部署后跑 `scripts/` 下回填脚本(拉近 400 自然日);API 计算时若某指数窗口起点缺数,取窗口内该指数**最早可得日**为基期并返回 `effective_start_date`,前端如实展示起算日,不虚构。
5. **区间收益口径对齐**:组合收益 = 窗口内 equity_curve 首/尾 agent_nav 之比 − 1(与净值图同源同口径);指数收益 = 同窗口首/尾收盘之比 − 1。对比基准日取「组合窗口首日」;指数若该日无值,向后找首个 ≤ 组合窗口首日的可得交易日(向过去找),保证不引入前视。
6. **跑赢判定 = 组合收益 > 该指数收益**(无中性带;展示层直读,不复用判定链 ±2% 带——那是 win/loss 判定口径,不迁移)。
7. **API 形态**:`GET /api/v1/track-record/index-compare?span=all|3m|6m|1y`,响应 `{span, window: {start, end}, agent_return, indices: [{code, name, return, effective_start_date, beat}], as_of, disclaimer}`;`beat: true|false|null`(null=该指数窗口内无数据,前端灰显)。

## Risks / Trade-offs

- **AKShare 限流**:日批新增 ~5 次指数调用 + 回填一次性 ~5 次长区间调用。回填脚本串行+退避;日批失败隔离(决策 3)。东财指数域 IP 封禁风险已有新浪回退(`fetch_index_kline` 内建)。
- **窗口起点不对齐**:组合首日为非交易日或某指数当日停更时,各指数 effective_start_date 可能不同——前端逐条展示起算日,避免「同一起点」误导。
- **净值曲线历史短**(当前仅 09-28 起):`span=all` 之外跨度可能不足,窗口按实际覆盖截断并在响应中带 `window` 实际值,前端标题展示实际区间而非请求跨度。
- **指数名硬编码中文**:随常量维护,不做 i18n(项目现状无 i18n)。
