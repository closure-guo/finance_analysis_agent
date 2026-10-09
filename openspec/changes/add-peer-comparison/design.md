# Design: add-peer-comparison

## Approach

三断点修复，对比以「主标的 + 对标股」形态在**单条管线**内完成：

1. **入口层**：deep_mode.md 新增对比意图分支，把「对比 A 和 B」编译成一次 `run_deep_analysis(stock_code=主标的, peer_codes=[...])`。`agent_factory.py` 给工具签名加 `peer_codes` 参数，LLM 显式传参优先于请求级闭包注入（闭包路径保留，供 API 直传/未来前端表单使用）。
2. **数据层**：`fetch_peer_data` 字段面分两组扩展——估值组（name/PE/PB/总市值）走现有 `_quote_via_chain` 三级链，总市值随 quote 快照带出（`market_cap` 元→亿归一）；财务组（营收同比/归母净利同比/毛利率/报告期）复用 `fetch_latest_period_snapshot`——与主标的最新报告期快照同函数同口径，天然免双口径风险；独立 try 边界实现字段组级降级。
3. **材料层**：compute 层新增格式化器 `format_peer_comparison(peer_financials)` → markdown 对照表（主标的首行标注），写入 `state.peer_comparison`——analysts.py:690 的既有注入点不动结构，标志位换真材料。基本面分析师 prompt 加消费指令（有同业材料时输出对比段 + 口径标注 + 缺失声明）。

## Key Decisions

1. **peer_codes 走 LLM 工具参数，而非仅请求闭包**：休眠根因就是 LLM 不可控（前端从不传 `AnalyzeRequest.peer_codes`）。两条路径并存、显式优先，兼容存量 API 调用。
2. **对比 = 单报告内嵌段，不并跑多管线**：避开 StreamRegistry 单 worker、LLM 预算治理（llm-budget-governance）、会话分组模型三大坑；主标的报告天然保留完整五层辩论与决策。
3. **格式化器落 compute 层、复用 `state.peer_comparison` 键**：与 `relative_valuation` 同处产出，最小 diff；analysts.py 注入点零结构改动。

## Alternatives Considered

- **L1 串行两跑 + 前端并排视图**：交互类变更（会话分组 + 并排渲染 + E2E 门禁 + 人工验证），工作量约 3 倍；等 L0 用真实使用验证对比价值后再立项。
- **L2 对比合成报告**（跑完两份后 LLM 生成对比结论）：跨 session 读取 + 新 LLM 节点 + judge 评估体系扩展，幻觉风险高；deferred。
- **仅请求级闭包注入（现状）**：前端不传参 = 永远休眠，否决。
- **管线原生多标的（state 多 code）**：图结构/缓存键/eval 体系全重构，相对收益过度。

## Risks

- **sina 财务接口限流**：财务组复用 `fetch_latest_period_snapshot`（利润表+资产负债表 2 请求/标的），1–3 只对标的 = 2–6 个额外请求。对策：实施期实跑验证限流阈值；财务组整体失败按字段组级降级兜底（spec 已契约化）；peer 上限 3 控制放大倍数。
- **总市值字段在 quote 回退链的覆盖度待验**（腾讯主源有，百度/东财回退待确认）：缺失时按字段级缺失标记处理，不阻断；实跑验证后如系统性不可得，用 openspec-update-change 校准 spec 再 archive。
- **主标的误识别**：search_stock 校验兜底 + 歧义时取第一只并明确告知可换视角（spec Scenario 已钉）。
- **context 预算**：对照表 ≤4 行 × ≤8 列，注入前过 analyst-context-budget 既有预算约束。
- **prompt 发布顺序**：deep_mode.md 与基本面分析师模板修改后必须 `deploy_prompts.py` 发布并指纹取证（production == 本地逐字）；历史坑——被拦时先取证再定向覆盖，勿用 sync 收编。
