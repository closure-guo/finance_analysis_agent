## 1. 阶段 0：自动重试停用 + 停滞保护 + 准入（当天）

- [x] 1.1 失败测试：`CITATION_AUTO_RETRY_ENABLED=False`（默认）时 `after_citation` 对 FAIL/覆盖缺口均返回 `render`；既有「返回 retry」类测试改为显式开启标志下运行（tests/test_routing.py）
- [x] 1.2 实现：`routing.py` 模块常量 `CITATION_AUTO_RETRY_ENABLED=False`、`CITATION_RETRY_ADMITTED_BUCKETS=frozenset()`；`after_citation` 停用分支直返 `render`；`route_to_analysts` 重试路径同受开关约束
- [x] 1.3 失败测试 + 实现：停滞保护——`citation_node` 在 retry 触发前记录目标分析师 markdown 哈希（`citation_retry_prev_hash`），重跑后哈希未变 → `citation_retry_no_progress=True` 立即放行（重试启用态下生效）
- [x] 1.4 观测不退化：停用态 fail_buckets/retry_targets/fail_rates/覆盖缺口照常写 state 与 trace（失败测试锁定）
- [x] 1.5 全量回归 + `uv run ruff check` + `uv run mypy`；提交并勾选 incident 026 第 0 步

## 2. 阶段 1：校验器归一（灭 39 条误报）

- [x] 2.1 fixture 固化：r2 的 39 条 FAIL 逐条落为测试 fixture（每条注明归因类别：路径/单位/词表/方向）
- [x] 2.2 失败测试 + 实现：日期 `YYYY-MM-DD` ↔ `YYYYMMDD` 行键双向匹配
- [x] 2.3 失败测试 + 实现：`quarterly_trend` 季度标签 ↔ `quarters` 位置索引映射
- [x] 2.4 数据根键 `unit` 注册表（先核实 akshare 各表单位）+ 失败测试 + 实现：interpretation 单位词缩放、无单位词 1e4/1e8 比值兜底（`unit_inferred` 标记）
- [x] 2.5 失败测试 + 实现：报表域 metric_name 与真实列名一致即判一致；`metric_vocab` 补列名别名
- [x] 2.6 失败测试 + 实现：指标 `signed` 注册；符号校验仅对有符号量生效；`direction` prompt 注释（deploy_prompts）
- [x] 2.7 注入式故障演练：fixture 注入 ±10% 真值偏差 → 必须 FAIL 且阻断层置位（回归测试长期保留）
- [x] 2.8 39 条 fixture 全量重判：预期全部转 PASS/UNVERIFIABLE-verifier-limit，输出终裁对照表落 `tests/validation/`

## 3. 阶段 2：注册表补全（23 条 UNVERIFIABLE → 可验）

- [x] 3.1 失败测试 + 实现：`garp_result`、`anomalies`、空值比率字段注册重算/集合比对
- [x] 3.2 r2/r3 的 23 条 UNVERIFIABLE 逐条重判并并入终裁对照表

## 4. 阶段 3：文本 claim 分型 + 回声匹配（75 条）

- [x] 4.1 失败测试 + 实现：`claim_type ∈ {entity, regulatory}` 或 `source_type=event` 不进 FAIL 分母、不计覆盖缺口
- [x] 4.2 失败测试 + 实现：回声匹配（标题/事件子串归一命中 → PASS(echo)），未命中 → UNVERIFIABLE(text) 单独计数
- [x] 4.3 r2 的 75 条舆情 claim 重判，统计回声命中率，落终裁对照表

## 5. 阶段 4：auto-claim 补覆盖缺口

- [x] 5.1 失败测试 + 实现：正文数字唯一匹配 state 结构化条目时合成 claim（`auto=True`，含单位缩放）
- [x] 5.2 r4 全量重扫：覆盖率 0.69–0.78 → 目标 ≥0.90（警告线）

## 6. 门禁三层分置 + 指标拆报

- [x] 6.1 失败测试 + 实现：`citation_blocked` / `citation_coverage_warn` / `citation_unverifiable_ratio`（分文本/未注册）；`citation_minor_fail` 退役
- [x] 6.2 失败测试 + 实现：`evals/run.py` 与 trace 元数据拆报（残余 FAIL / verifier_normalized_count / 文本与未注册 UNVERIFIABLE），`citation_pass` 语义变更并在报告注明基线切点（incident 026）
- [x] 6.3 前端/报告若呈现 citation_pass：核对展示语义，不适用则标注

## 7. 验证与收口

- [x] 7.1 全量门禁（pytest -m "not live" + ruff + mypy）
- [x] 7.2 重跑一轮 dataset 实验（r4），产出拆报指标与终裁对照表合并报告，落 `docs/evals/`
- [ ] 7.3 archive 前置核对（待 owner 终裁 22 条后）：tasks 全勾 + 验证记录 + 规范 sync
