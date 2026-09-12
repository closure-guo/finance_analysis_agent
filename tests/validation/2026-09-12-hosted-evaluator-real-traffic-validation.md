# 验证报告: enable-hosted-evaluator 真实流量监控验证（2.2 + 3.2）

**日期**: 2026-09-12
**验证人**: [agent]（真实链路执行 + 证据落档，终判待 owner 签字）
**关联 delta**: openspec/changes/enable-hosted-evaluator/
**前置**: owner 已恢复 LLM 余额并在 UI 重新开启 evaluator（4 条 job_configuration 均 ACTIVE，实测确认）

## 1. evaluator 配置核实（2.2）

- 4 个 evaluator（report_relevance / debate_quality / decision_grounding / consistency）状态 ACTIVE、采样 10%、delay 30s（Postgres job_configurations 实测）
- 模板快照：docs/evals/hosted-evaluator-template.md 已含 2026-09-07 上线快照 + 2026-09-12 判别键修订注记
- **发现并修复**：3.225.7 上 hosted 分数落库 `config_id=NULL`（分数名带中文后缀、`source=EVAL`），原「UI evaluator 分数带 configId」假设不成立，`poll.py` 的 configId 过滤失效 → 已改 `source=EVAL` 判别（commit 5e6008a，TDD 3 例）

## 2. 端到端真实流量验证（2.2 / 3.2）

触发真实 deep 分析（`/api/analyze`，贵州茅台 600519），trace `c7e988cc91d0d21c909fc0d176c677ce`：

| 环节 | 结果 |
|---|---|
| 管线完成（根 span endTime 03:04:19Z，metadata.report_markdown 9183 字符） | ✅ |
| 4 个 evaluator 全部触发（job_executions 4×COMPLETED，无错误） | ✅ |
| 4 维分数落库（ClickHouse source=EVAL：report_relevance 5 / debate_quality 4 / decision_grounding 4 / consistency 4） | ✅ |
| 轮询报告（poll.py，source=EVAL 过滤）：24h 窗口 4 条，均分 4.25，无告警 | ✅ reports/hosted-eval-report-20260912.md |
| 验证后采样已还原 10%（临时 100% 仅覆盖本次验证，先例同 09-07 报告） | ✅ |

验证方法说明：临时采样 100% 经 DB UPDATE + worker 重启（本地 dev 实例，先例为 09-07 UI 操作），验证后已还原并重启。

## 3. 口径对齐（spec 1.3，MAE≤1.0）

`tests/scripts/align_hosted_offline.py`（新增）：hosted 已打分 trace × 离线 judge（当前 rubric）同 trace 重打分配对。

- **32 对，MAE = 1.0312，超阈值 1.0，drift = True**（reports/hosted-offline-align-20260912.json）
- 归因（分桶先行，指标不入处置）：**hosted 模板版本落后于离线 rubric**——
  - consistency：hosted 模板无 v2「approve 批准对象」语义条款，系统性给高分（4 对 hosted=5 / offline=4），与 round5 校准发现的原 v1 病灶一致；
  - decision_grounding：hosted 模板为 v3（无 v6 的【风控指标】【风险辩论记录】节）；
  - 另有材料映射差异（hosted 直读根 span metadata，离线走 extract_judge_vars 预算截断）。
- **处置建议**（挂在终裁桶上，不自动执行）：owner 在 UI 将 4 条 evaluator 模板升级到当前离线 rubric 版本（consistency v2 语义 + decision_grounding v6 节构），升级后重跑 align 复测 MAE。降级模式无公共 API，模板升级只能 UI 手工操作。

## 4. 已知边界

- hosted 与离线的 trace 人群天然错位（10% 采样 vs 数据集实验批），口径对齐依赖「hosted 打分的 trace 重建 state 重打离线分」，experiment-item-run trace 无 node 级 observations 无法重建——本报告对齐样本为 API 路径 deep run（含 09-08 时代 6 条 + 本轮 1 条的可配对维度）。
- 真实流量监控的长效运行（poll.py 定时）未配置调度，当前为手动执行。

## 结论

[ ] 2.2 / 3.2 验证通过，drift 处置（模板 UI 升级）由 owner 拍板后可 archive
[ ] 存在失败项，需修复后重新验证
