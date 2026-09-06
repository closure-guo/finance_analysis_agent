# calibrate-fm-approval 验证报告

- 日期：2026-09-04
- 提交：225b10d（取证 + return 回路反馈修复 + FM 决策评估门禁）

## 取证结论（本 delta 的核心产出）

- Langfuse 153 条 fund_manager trace：approve 81（53%）/ return 44 / reject 24
  ——「FM 从不 approve」假设证伪；历史战绩空白是落库缺陷（已修）造成的错觉
- 「连续只见 reject」窗口 = 力鼎光电（真实计算回撤 41.2%/波动 75.6%）反复重跑，
  FM 依风控职责正确否决；真实缺陷 = return→trader 重跑未携带 FM 退回理由
- 决策：不放松风控（无 approve 占比下限），修复反馈回路 + 建立守门

## 自动化验证

- 全套后端 pytest：1912 passed（trader 反馈注入 3 例 + FM 回路契约 + fm_decision
  度量 15 例 + nightly @live 1 例）
- trader context 注入语义：return 时含「基金经理退回意见」，approve/reject/空
  理由不注入（TDD red→green）
- 评估模块：分布聚合（按日分桶、无 trace 报样本不足）、风控否决召回（高风险
  approve 即违例，fixtures 驱动）、理由完整门禁（live 数据 0 缺失）
- 本机 @live 真跑：149 条样本 approve 54%/return 30%/reject 16%，报告落
  reports/fm-decision-report-20260904.md
- ruff / mypy 全绿；delta 过 strict

## 待人工验证

1. 真实链路 return 回路（tasks 4.3，需 LLM 余额）：deep 分析触发 FM return →
   trader 重跑方案是否体现改进 → Langfuse trace 佐证
2. nightly CI 的 live job 需补 LANGFUSE secrets 才能全量生效（仓库管理员）
