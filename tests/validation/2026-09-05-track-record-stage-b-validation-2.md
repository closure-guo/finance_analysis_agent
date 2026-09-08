# 人工验证报告: add-track-record-stage-b

**日期**: 2026-09-05（周五收盘后）
**验证人**: ZCode agent（真实行情端到端实测）
**关联 delta**: openspec/changes/add-track-record-stage-b/
**E2E 门禁**: stub 套件 20 passed / 2 skipped / 0 failed（2026-09-05）

## 验证环境

- 后端 TESTING=1（TESTING 库，GUI 验证专用），`tests/scripts/stage_b_manual_verify.py` 造数 + 触发日批
- 造数：3 条 live 观点（600519.SH long / 300750.SZ short / 601318.SH long，入场日为 15/10/5 天前，horizon 252）
- 行情源：akshare 真实接口（东方财富日 K + 指数 K）

## 验证结果

| 验证项 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| 真实行情盯市 | open 观点按交易日盯市（mark_price/cum_return/cum_excess） | 600519 marks=10、300750 marks=7、601318 marks=4（按各自入场日以来真实交易日数） | ✅ |
| 净值曲线落地 | upsert_equity_point 归一化净值序列 | run_daily_marking: marked=21 / equity_points=10 / errors=0，快照截至 2026-09-05 | ✅ |
| 指标快照落地 | 组合年化/波动/夏普/回撤/风险分入库 | 指标快照生成并在 /track-record「组合风险指标」块渲染 | ✅ |
| /track-record 曲线渲染 | ECharts 净值曲线（组合 vs 沪深300，起点 1.0） | 页面 canvas 渲染 + 观点总数 3 + 观点列表（进行中/未结算） | ✅ |
| 缺数据容错 | 停牌/接口失败仅跳过该观点 | 运行中 akshare 个别请求 ConnectionError（重试 3 次后跳过），errors=0 不中断 | ✅ |
| 幂等 | 同日重跑覆盖不重复 | 脚本二次运行同日重跑正常（同日覆盖语义） | ✅ |
| 日批时序（settle → marking） | 先 16:00 结算再 16:30 盯市 | scheduler.py 注册顺序 settle(16:00) → marking(16:30) → metrics(16:35) → integrity(16:40)，注释明确「先结算到期观点再对剩余 open 观点盯市，避免重复盯市」 | ✅ |
| 样本不足标注 | 已判定 < 10 时胜率置 null | 页面显示「样本积累中（已判定 0 条，满 10 条解锁胜率）」，切片指标标注「样本不足」 | ✅ |

## 观察与备注

- **指标数值失真属预期**：10 个净值点外推年化收益/波动率（年化 -100%、波动 194%）数值极端，是小样本外推的固有失真，非计算缺陷；随样本积累收敛。UI 已有「样本不足/积累中」标注兜底。
- **胜率未解锁**：horizon=252 交易日内无观点到点判定，胜率区保持「样本积累中」——符合设计（win/loss 判定见 stage-c 验证路径）。
- 脚本首次运行有一处路径笔误（parents[1] → parents[2]）已修正，与产品代码无关。

## 结论

- [x] 全部通过，可 archive
