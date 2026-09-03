# 消融实验试跑记录：pilot.md

**日期**：2026-09-02
**目的**：`evals/ablation.py` 首跑，产出"辩论层价值"第一份真实数据（简历关键素材）
**产物 JSON**：`reports/ablation/pilot-20260902-152818.json`（+ 断点续跑台账 `reports/ablation/resume.json`）
**驱动脚本**：`tests/scripts/ablation_pilot.py`（自驱循环 + 断点续跑 + usage 记账，不改 evals/ablation.py）

## 配置（硬上限内）

| 项 | 值 |
|---|---|
| 标的 | 002412 汉森制药 / 600519 贵州茅台 / 300308 中际旭创（3 只） |
| 变体 | analysts（4 分析师直出）/ plus_debate（+Bull/Bear 两轮辩论 + research_manager）/ full（完整五层，含两轮风控辩论 + 基金经理） |
| 重复 | 3 次/（标的 × 变体），共 27 run |
| 分析模型 | **glm-5.3**（火山方舟；.env 生产默认——用户裁决：试跑与生产同模型，数字可迁移） |
| judge | deepseek-v4-flash（火山方舟；与分析模型分离，保持独立性） |
| 统计 | 同标的同变体 3 次取中位；层间差异用配对 bootstrap B=10,000（`evals/stats.py`）95% CI |
| 快照对齐 | 每标的三变体共用同一 fetch_data+compute_metrics 快照（snapshot_digests 落盘可验） |

## 结果总表

| 变体 | citation_pass | coverage | judge 中位（rel/辩论/grounding/一致） | token 成本 | 增量效果 vs 上一层（95% CI） |
|---|---|---|---|---|---|
| analysts | 3/9 = **33.3%** | 0.657 | 5.0 / — / — / — | 632,293（64 次调用） | 基线 |
| plus_debate | 2/9 = **22.2%** | 0.545 | 5.0 / 5.0 / 5.0 / 4.0 | 662,409（105 次调用） | 辩论层：report_relevance Δ0 CI[0,0]、citation_pass ΔCI[-0.333, 0] → **未获统计支持** |
| full | 0/9 = **0.0%** | 0.662 | 5.0 / 5.0 / 4.0 / 4.0 | 1,076,984（230 次调用） | 风控+PM 层：**decision_grounding Δ-1 CI[-1,-1] → 显著退步**；debate_quality CI[0,1]、consistency CI[-1,1]、citation_pass ΔCI[-0.333,0] → 未获统计支持 |

**usage 汇总（真值，0 条估算）**：482 次 LLM 调用 / 2,555,731 token（1,943,510 输入 + 611,081 输出）；单 run 均值约 17.9 次调用 / 94.7k token。

## 结论措辞（严格按 CI 纪律，无修饰）

1. **辩论层（analysts → plus_debate）**：judge 的 report_relevance 与 citation_pass 率增量的 95% CI 均含 0 → **该层价值未获统计支持**。
2. **完整层（plus_debate → full）**：decision_grounding 增量 CI = [-1, -1]（排 0）→ **显著退步**；其余维度 CI 含 0 → 未获统计支持。
3. **整体 citation_pass 偏低**（33%→22%→0%）：所有变体下 glm-5.3 产出的 claim 大量未通过校验器（FAIL 分桶未在本 pilot 展开归因）——**这是 pilot 暴露的现象，不构成"辩论层导致幻觉率上升"的因果结论**（样本小 + 未分桶），留作 follow-up issue。

## 成本实测

| 变体 | 调用次数 | token 合计 | 单 run 均值 |
|---|---|---|---|
| analysts | 64 | 632,293 | 70,255 |
| plus_debate | 105 | 662,409 | 73,601 |
| full | 230 | 1,076,984 | 119,665 |

（glm-5.3 无思考链，输出 token 显著小于此前 deepseek-v4-flash 误用轮的实测，见成本对照。）

## 环境偏差（诚实披露）

1. **分析模型**：glm-5.3（ark）。此前两轮曾误用 deepseek-v4-flash 作分析模型（deepseek-chat 官方 key 失效后的错误替代），**已弃用并重跑**；本文件数据全部为 glm-5.3。
2. **judge 端点**：zen → ark（zen 余额见底），judge 模型不变（deepseek-v4-flash）。
3. **数据源**：K 线/指数走新浪（东财 push2his 本机不可达，见 issue #102/#103）；新闻/实时行情按空降级。
4. **重试与断点**：pilot 驱动含瞬时故障指数退避重试（ark burst/半僵流）与逐 run 断点续跑（2026-09-02 补）——本组 27 run 全程 0 次限流/超时崩溃。

## 简历素材对照（素材 3 的真实数据替换）

> 通过数据对齐消融实验（三变体 × 同 state 快照 × 3 次重复，配对 bootstrap B=10,000）量化多智能体辩论层的增量价值：Bull/Bear 辩论层增量未获统计支持（CI 含 0），风险辩论+基金经理层使 decision_grounding 显著退步（95% CI [-1,-1]）；据此裁剪管线可节省约 41% token（full vs analysts：1,076,984 vs 632,293）。

---

# 附录 B：90-run 权威消融（2026-09-03，含 D6，n=10）

## 配置
3 标的 × 3 变体 × 10 重复 = 90 run，glm-5.3，**含 D6 打回补 claim**（与 pilot 差异）。

## 变体（n=30 each）

| 变体 | citation_pass | coverage | judge 中位 | tokens/run |
|---|---|---|---|---|
| analysts | 10% | 0.8174 | 5.0 / — / — / — | 120,657 |
| plus_debate | 13% | 0.7928 | 5.0 / 5.0 / 4.0 / 4.0 | 130,169 |
| full | 13% | 0.7678 | 5.0 / 5.0 / 4.0 / 4.0 | 169,308 |

## 层间增量（配对 bootstrap B=10,000，95% CI）

| 层 | 维度 | Δ | CI | 结论 |
|---|---|---|---|---|
| 辩论层 | report_relevance | 0.0 | [0,0] | 未获统计支持 |
| 辩论层 | citation_pass | — | [0,0.1] | 未获统计支持 |
| 完整层 | report_relevance | 0.0 | [0,0] | 未获统计支持 |
| 完整层 | debate_quality | -0.17 | [-0.5,0] | 未获统计支持 |
| 完整层 | **decision_grounding** | **+1.33** | **[0,3]** | 未获统计支持（正向趋势） |
| 完整层 | consistency | +0.67 | [0,1] | 未获统计支持 |
| 完整层 | citation_pass | — | [-0.1,0.1] | 未获统计支持 |

## 关键结论

1. **pilot 的「full 层 decision_grounding Δ-1 显著退步」是伪影（#112 预判证实）**：
   n=10 下变为 **Δ+1.33 CI[0,3]**（正向但不显著）。#112 修复（plus_debate 不再评该维）
   消除「宽容评虚层 vs 挑剔评真层」的不对称。
2. **所有层间增量均未获统计支持**（CI 含 0）——辩论层/决策层在本样本下的增量价值无统计证据。
3. citation_pass 三变体均低（10-13%），#105 契约噪声仍主导（仅 #109/#111/#112 部分修复）。
4. **成本**：总 2,059 次调用 / 13.16M token（D6 使单 run 成本较 pilot +45~69%）；裁剪完整层省 **28.7%** token（pilot 的 41% 为旧管线数字，作废）。
5. judge 维度按 #112 适用性过滤（analysts 仅 relevance，plus_debate 仅 relevance+debate_quality）。

## 简历素材 3 更新（n=10 权威版）

> 通过数据对齐消融实验（三变体 × 同 state 快照 × 10 次重复，配对 bootstrap B=10,000）
> 量化多智能体辩论层的增量价值：**辩论层与完整层增量均未获统计支持（95% CI 含 0）**；
> 先前 pilot 的「完整层 decision_grounding 显著退步」在修复评估缺陷（#112）后证实为伪影，
> n=10 下转为正向但不显著（Δ+1.33，CI[0,3]）。据此裁剪管线可节省约 **29%** token。
