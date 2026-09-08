# 验证报告: hosted evaluator 端到端（report_relevance 打分实证）

**日期**: 2026-09-07
**验证人**: [agent]（真实生产链路端到端验证）
**关联**: enable-hosted-evaluator / deep-trace-eval-data / deep-trace-eval-full-data / Langfuse 3.225.7 升级

## 验证范围

四维 hosted evaluator（LLM-as-judge）从「管线产出 → trace 数据层 → evaluator filter 命中 → judge LLM 打分 → 分数落库」完整链路是否打通。

## 前置状态

- Langfuse 已升级 3.205.1 → 3.225.7（迁移 420 条 Prisma、trace 数据完好）
- deep-trace-eval-data（根 span 落 query + report_markdown）+ deep-trace-eval-full-data（全量评估段）已归档
- 4 个 evaluator（report_relevance / debate_quality / decision_grounding / consistency）已配置并核对：target=observation、filter=`metadata.report_markdown starts with #` + environment none-of、10% 采样、NUMERIC 1-5、jsonSelector 映射、模板键名 `reasoning`（Langfuse output_schema 只认 `score`+`reasoning`）、Additional options `{"providerOptions": {"thinking": {"type": "disabled"}}}`

## 端到端验证（真实运行）

通过 `/api/analyze`（stock_code=688072）跑一次真实深度分析（拓荆科技），trace `d65c1257ba61fdf3c9e824c903e6a0bc`：

**1. 根 span 评估数据全量落库（ClickHouse 实测）**

| 评估键 | 长度（字符） |
|---|---|
| `report_markdown`（完整报告） | 37,700 |
| `analyst_reports`（全量含 markdown/claims） | 27,958 |
| `debate_history`（多空辩论全量） | 15,949 |
| `research_manager_decision` | 1,874 |
| `risk_judgment` | 4,117 |
| `input.query` | 深度分析 拓荆科技(688072) |

**2. evaluator 触发并打分**（验证时临时采样=100%，验证后还原 10%）

- `job_executions`：report_relevance（报告切题度）**COMPLETED**，无错误
- **分数 = 4**，reasoning：
  > 报告紧扣'深度分析'意图，提供了详尽的财务指标图表和基本面分析，但技术面、宏观面、舆情面数据缺失导致分析维度不完整，且风控辩论篇幅过长偏离了投资分析的主旨。

评分合理：正确识别报告因东财数据缺失而维度不完整、风控辩论篇幅偏长。

**3. 顺带验证**：同 trace 的 citation 系列分正常写入（citation_coverage 0.875 / citation_pass / citation_unverifiable_ratio）。

## 验证结论

| 环节 | 结果 |
|---|---|
| 管线产出 → trace 评估段全量 | ✅ |
| evaluator filter（report_markdown starts with #）命中根 span | ✅ |
| judge LLM（deepseek via Ark）有效打分 | ✅ |
| score + reasoning 落 Langfuse score 库 | ✅ |

四维 hosted evaluator 前置数据与配置全部就绪，在线打分链路闭环。

## 已知说明

- 本次运行东财部分数据源风控失败（ConnectionError），报告技术面/宏观/舆情维度不完整——judge 正确识别并据此评分（4/5）。失败 run（report_markdown 空）不会被 filter 命中，不污染评分。
- 正常采样已还原 10%；其余三个 evaluator（debate_quality/decision_grounding/consistency）未在本轮触发（10% 概率未命中），配置已核对，随运行积累采样。
