# Proposal: clear-valuation-chain-debts

## Why

delta update-financial-freshness-and-valuation 实施与终审过程中确认了一批挂账（已记录于其验证报告「遗留」节与 incident 033 后续清单）：其中两项是行为契约缺口（GARP 仅 PE 做了诚实分桶，growth/ROE/负债率的缺失仍被渲染成比较失败、NaN 被伪装成通过；同业财务数据抓取 `fetch_peer_data` 自 P1 起从未实现，生产中相对估值名存实亡），其余为实现级缺陷（fetch 层 NaN 透传、报告披露节编号与「暂缺」文案、api 健康度进度行死代码、图通道门禁未覆盖 fetch 产出键）。本变更一次性清账，避免遗留静默腐烂。

## What Changes

- GARP 诚实分桶推广到全部四个输入：growth/ROE/负债率在缺失或 NaN 时输出「X 数据缺失（未参与比较）」+ missing 标注，MUST NOT 渲染成「X <= 15%」类比较失败，NaN MUST NOT 伪装成通过
- 实现 `AKShareClient.fetch_peer_data(stock_codes)`：逐标的复用 `fetch_stock_quote` 回退链取 PE/PB/名称，返回 `_build_peers_list` 契约的 DataFrame；单标的失败跳过不拖垮整批，全失败降级 None（fetch 层既有 optional 语义）
- fetch 层出口 NaN 归一：`fetch_quarterly_income` 数值列（环比/同比/营收同比）NaN → None，落实「不产出伪值」既有契约
- 报告披露节改为编号章节（复用 `next_title` 机制），「暂缺」不再携带单位后缀
- 修复 api.py SSE 进度「健康度 X」恒 None 的死代码（`hs.get("score")` → `hs.get("total")`）
- 图通道门禁（agent-node-contracts「节点产出键 ⊆ AnalysisState」）从「至少 compute_metrics」扩展到覆盖 fetch_data 产出键（latest_period_snapshot 已实测无丢失，属守卫补强）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `valuation-signal-integrity`: 「估值缺数据的诚实文案」扩展——诚实分桶从 PE 推广到 GARP 全部四个输入（growth/ROE/负债率），NaN 显式视同缺失
- `analyst-data-sources`: 新增「同业财务数据获取」requirement——fetch_peer_data 的实现、降级与消费契约（相对估值从「可计算时」变为「有 peer_codes 时可计算」）

## Impact

- `src/finance_agent/metrics/garp.py`：三分支推广 + `_clean_num` 应用到全部输入
- `src/finance_agent/data/akshare_client.py`：新增 `fetch_peer_data`；`fetch_quarterly_income` 出口 NaN 归一
- `src/finance_agent/nodes/report.py`：披露节编号化 + 暂缺文案
- `src/finance_agent/api.py`：health_score 进度行取值修正
- `tests/test_graph_5layer.py`：门禁扩展 fetch 产出
- 非交互类变更，不触发 E2E 门禁；无 prompt 变更（不涉 deploy_prompts）
