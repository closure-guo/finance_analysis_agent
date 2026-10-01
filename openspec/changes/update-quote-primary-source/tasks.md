# Tasks: update-quote-primary-source

- [ ] 腾讯单标的抓取函数 `_fetch_tencent_quote` 落地：位序常量表 + GBK 解析 + market_cap 亿→元归一 + PE 不消费；金样本单测（sh688072 串 fixture：price/market_cap/PB/换手率映射断言 + 缺字段/串变形返回 None）
- [ ] `fetch_stock_quote` 主源链切换：腾讯 → 东财 spot（回退1）→ 百度+腾讯日线（回退2）→ 仅名称；东财路径仅在主源失败后触发；`sources_seen` 主源记 `tencent`
- [ ] `fetch_peer_data` 复用新链（逐标的单请求），共享 spot 表优化保留在东财回退路径
- [ ] 口径裁决单测落地：双源形（腾讯/百度）PB 与 market_cap 各自期望值钉死，跨源不融合；valuation-signal-integrity 既有 derived_ttm 路径回归全绿
- [ ] 数据源监控面：`sources_seen`/监控快照可见 `tencent` 主源标注；东财非行情域（解禁/新闻/研报）健康度列入观测项
- [ ] 文档连锁：`docs/evals/metrics.md` §1 登记 quote 主源切换切点；`docs/incidents/033` C1 保留意见改写为「东财回退路径解封后抽验一次」
- [ ] 全管线人工验证：688072 封禁环境实跑（腾讯主源命中），披露节/GARP/健康度/估值行为与 2026-10-01 基线等价；报告落 `tests/validation/`
- [ ] 静态门禁：全量 pytest / ruff / mypy 基线无增量
