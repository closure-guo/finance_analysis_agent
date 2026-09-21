# decision-semantics r5 重评收口报告（harden 6.2 / 6.3）

**status**: active

日期：2026-09-12｜run：`baseline-decision-semantics-r5`（03:17Z，HEAD fa9f72b+当日 5e6008a/9af47ff/5d80058，均不含管线行为变更）｜模型 glm-5.3 + judge deepseek-v4-flash（与 r3/r4 同配置）

## 1. 6.2 重评执行

r3 trace 无 node 级 observations、judge 变量无法用当前代码重渲染（原 debate 消息预算 6000，fa9f72b 后 24000），故按 design.md 迁移计划走全量 dataset 重跑（17 项：9 deep + 5 quick + 3 skip）。

**健康检查**：

- 分数齐全度：9/9 deep 全四维、5/5 quick report_relevance，judge_failures=0
- confidence 落库：43/45（96%），范围 0.70–0.98，无 <0.5 低置信项（无残缺输入幻觉信号）
- 契约抽验（consistency judge 材料，trace 6868c43a）：FM 操作定性（action）✓、风险辩论尾部标签 ✓、FM 理由可见 ✓（裁决节边界标签为标注材料层修复，judge prompt 本就不含——抽验判据已修正）

**均值对比**（deep 9 条）：

| 指标 | r3（02:08Z） | r4（07:36Z，citation 收口轮） | r5（本轮） |
|---|---|---|---|
| consistency | 4.67 | 4.89 | **5.00** |
| decision_grounding | 4.33 | 4.00 | **4.22** |
| debate_quality | 5.00 | 5.00 | 5.00 |
| report_relevance | 5.00 | 4.93 | 5.00 |
| citation_coverage | — | 0.837 | 0.879 |
| citation_blocked | — | 6/9 | **4/9** |
| analyst_true_fail | 混在 FAIL | 1.89/条 | **0.78/条** |
| verifier_normalized | — | 47/轮 | 8.0/轮（口径：r4 表内数字为全轮合计，r5 为均值，不可直接对比） |
| judge_failures | 0 | 0 | 0 |

## 2. 6.3 对比归档与解读

- **consistency 4.67→5.00**：FM 序列化含 action/理由后，judge 可见「FM 批准的对象与理由」，v2 语义条款的修正方向在重评中得到保持；无 3 分以下项。
- **decision_grounding 4.00→4.22**：r5 扣分集中在 evidence_refs 个别来源偏差（如「尾部风险论据实来自保守方而非 risk_metrics」），rubric v6 语义核对按设计工作。
- **analyst_true_fail 1.89→0.78/条**：方向向好，但**本轮东财数据源大面积不可用**（stock_zh_a_hist/individual_info 全失败，百度+腾讯回退），claim 总量与结构受数据降级影响，不能归因单一变量——该改善不作为修复效果的证据，待数据源正常轮次确认。
- **quick report_relevance 全 5 分**：与 round5 人工标注的口径分歧（人工 1 vs judge 5）在 rubric v3「口径必读」下仍存在——v3 已含「合规约束下如实说明=已回答」条款，judge 按 v3 判 5 属口径内行为；最终裁决待 round7 人工盲标回填（6.4，report_relevance/debate_quality judge 零方差维度以 MAE/方向一致率为主）。
- round5 盲标表保持既有口径作为「改动前基线」，未做混合对比（design D6）。

## 3. rubric v2「评分前必读」段简化评估（6.3 后半）

结论：**不简化，不升版**。三行内容逐一对应实测病灶（①approve 对象=方案非裁决票、②watch+approve=批准观望、③真冲突定义），缺任一行即复现 round5 的 7/11 误判；段长约 500B / 17100B prompt（<3%），简化收益可忽略而回归风险实在。consistency rubric 维持 v3。

## 4. 台账与后续

- metrics.md §2.1 时间线已加 r5 行；runs.jsonl 已追加。
- 6.2 ✓ 6.3 ✓ 已勾选；**6.4（round7 盲标回填 + measure）仍待人工**——round7 表 41 行锁定 r3 窗口，owner 标注中。
- 环境备注：东财数据源当日不可用是本轮最大混淆变量；附孤儿 trace 说明——首个被中止的重名 r4 run 遗留 1 条无主 experiment-item trace（c5715314，无 dataset run 关联，无 judge 分之外的引用价值），同名 dataset run 记录已清理。
