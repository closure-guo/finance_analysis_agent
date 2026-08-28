# Evals 数据集基线指标登记

> 本文件是 **a-share-analysis-v1 数据集基线指标的持久登记**（被 git 跟踪）。
> 实验原始 JSON 落在 `reports/evals/*.json`（gitignored 本地产物），跑批后按本文件规则回填登记。
> 基线口径：同数据集、同 evaluator 套件、GLM（方舟 plan/v3）管线全链路（5 层）的运行均值。
> 用途：delta 收益判定、judge 校准（`evals/run.py` 产出 JSON 是 Req 5 人工校准输入）、模型/提示词漂移监测。

## 数据集

| 项 | 值 |
|---|---|
| 名称 | `a-share-analysis-v1`（langfuse dataset） |
| seed 源 | `evals/dataset_seed.py` → `evals/dataset_items.json`（幂等，去重键 `(query, mode)`） |
| item 数 | 16 |
| 组成 | 7 deep（出分）+ 4 quick（出分）+ 2 clarify（「帮我分析一下这只股票」「现在适合入场吗」，应反问澄清不出报告）+ 3 follow_up（需前一会话上下文，实验独立执行不出分） |
| 评分维度 | section_coverage / ticker_match（确定性）+ report_relevance / debate_quality / decision_grounding / consistency（judge，deep 才有 debate/decision/consistency） |

## 当前基线（最近一次完整管线基线）

**实验**: `baseline-v2-ark-20260824-104523`（2026-08-24 10:45 起，57 分钟，16 items）
**JSON**: `reports/evals/baseline-v2-ark-20260824-104523-20260824-114230.json`（gitignored）

| 维度 | 均值 | 说明 |
|---|---|---|
| report_relevance | 4.4545 | n=11 |
| decision_grounding | **1.5714** | n=7，5 条 =1.0（无结构化引用时代的老问题点） |
| debate_quality | 4.5714 | n=7 |
| consistency | 3.4286 | n=7 |
| section_coverage | 0.881 | n=7 |
| ticker_match | 1.0 | n=11 |
| judge_failures | 0 | |

### 基线逐条 deep（decision_grounding）

| item | dg |
|---|---|
| 全面分析中芯国际(688981) | 2.0 |
| 贵州茅台现金流 | 1.0 |
| 全面分析招商银行(600036) | 1.0 |
| 全面分析比亚迪(002594) | 1.0 |
| 全面分析平安银行(000001) | 4.0 |
| 全面分析宁德时代(300750) | 1.0 |
| 全面分析贵州茅台(600519) | 1.0 |

## 历次基线（漂移/历史上下文）

完整均值仅记录 score 非空的维度；早期运行维度不全（judge 迭代中）。

| 实验 | 日期 | report_relevance | debate_quality | decision_grounding | consistency | section_coverage | judge_failures |
|---|---|---|---|---|---|---|---|
| baseline-v1-20260816-101501 | 08-16 | — | — | — | — | 0.9238 | 28（judge 初版） |
| baseline-v2-ark-20260816-194606 | 08-16 | 4.2727 | 1.0 | 1.8571 | 3.7143 | 1.0 | 0 |
| baseline-v2-ark-20260816-205110 | 08-16 | 4.5455 | 4.0 | 2.8571 | 4.1429 | 0.9238 | 0 |
| baseline-v2-ark-20260817-235841 | 08-17 | 4.1429 | 3.7143 | 4.0 | 2.2857 | 0.7095 | 0 |
| baseline-v2-ark-20260823-182457 | 08-23 | — | — | — | — | — | 0（仅 ticker_match，行级失败） |
| **baseline-v2-ark-20260824-104523** | **08-24** | **4.4545** | **4.5714** | **1.5714** | **3.4286** | **0.881** | **0** |

> 注意：decision_grounding 在不同基线日波动大（1.57~4.0，08-17 曾达 4.0），判定 delta 收益应以同日对照实验为准，不以跨日均值作绝对基准。

## 对照实验（delta 收益证据）

**实验**: `improve-dg-evrefs-20260824-135439`（2026-08-24 13:54 起，33 分钟，16 items，同日同数据集）
**JSON**: `reports/evals/improve-dg-evrefs-20260824-135439-20260824-142753.json`（gitignored）
**变更**: `improve-decision-grounding` delta（TradeDecision `evidence_refs` 结构化论据引用 + decision_grounding rubric 对齐 + analyst_reports 保留 claims 数值）

| 维度 | 基线 08-24 | 对照 08-24 | 变化 |
|---|---|---|---|
| decision_grounding | 1.5714 | **4.1429** | +2.5714 |
| report_relevance | 4.4545 | 5.0 | +0.55 |
| consistency | 3.4286 | 4.2857 | +0.86 |
| debate_quality | 4.5714 | 4.1429 | −0.43（开环波动） |
| section_coverage | 0.881 | 0.8286 | −0.05（开环波动） |
| judge_failures | 0 | 0 | 持平 |

逐条 dg：中芯国际 2.0→4.0、茅台现金流 1.0→4.0、招商银行 1.0→4.0、比亚迪 1.0→4.0、平安银行 4.0→4.0、宁德时代 1.0→5.0、贵州茅台 1.0→4.0（7/7 ≥4）。

**实验**: `post-prompt-enhancement-v2-langfuse`（2026-08-25 10:14 起，16 items）
**JSON**: `reports/evals/post-prompt-enhancement-v2-langfuse-20260825-112800.json`（gitignored）
**变更**: `enhance-agent-prompt-quality` delta（分析师方法论+反幻觉硬规则、辩论对抗指令、决策语义契约、research_manager 评级表态、摘要接地）同步至 Langfuse production label（prompt_versions 全 ver=2）

| 维度 | 基线 08-24 | evrefs 08-24 | 本轮 v2 08-25 | 变化(vs 基线) |
|---|---|---|---|---|
| decision_grounding | 1.5714 | 4.1429 | **4.0** | +2.43 |
| report_relevance | 4.4545 | 5.0 | 4.9091 | +0.45 |
| consistency | 3.4286 | 4.2857 | 4.0 | +0.57 |
| debate_quality | 4.5714 | 4.1429 | 4.0 | −0.57（开环波动） |
| section_coverage | 0.881 | 0.8286 | 0.8762 | −0.005 |
| judge_failures | 0 | 0 | 0 | 持平 |

逐条 dg（本轮 v2 全 4.0）：中芯国际 4.0、茅台现金流 4.0、招商银行 4.0、比亚迪 4.0、平安银行 4.0、宁德时代 4.0、贵州茅台 4.0（7/7 =4.0，无 <4；对比基线 5/7 =1.0）。

> 注意：① 首次实验 `post-prompt-enhancement-v1-20260825-102839` 因 Langfuse production label 为旧 ver=1（无 evidence_refs/本轮增强）而测的是旧 prompt，结果不反映本轮变更，仅作 prompt 版本漂移证据。② 本轮 debate_quality/consistency 相对 evrefs 有开环波动（−0.14/−0.29），dg 维持 4.0 档；判定增量以 dg 稳定 ≥4.0 与 judge_failures=0 为准。

## 登记规则

1. 实验完成后，跑批脚本（`evals/run.py`）将 `means` 与 `rows` 写入 `reports/evals/<实验名>-<ts>.json`。
2. 人工将关键均值回填到本文件的「当前基线」或「对照实验」一节（或在跑批脚本中自动化回填）。
3. 基线轮换：新的全链路基线跑完且无异常（judge_failures=0）时，替换「当前基线」节，旧基线移入「历次基线」表。