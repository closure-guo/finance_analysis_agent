# harden-citation-semantic-coverage 三标的冒烟验证（2026-09-01）

**分支**: `feat/harden-citation-semantic-coverage`（验证时 HEAD `d42b60d`）
**驱动**: `tests/scripts/verify_smoke_harden_citation.py`（触发 → 轮询终态 → Langfuse 取证）
**产物**: `reports/citation_smoke_harden_20260901-102940.json`（首轮）/ `-111635.json`（修复后）；`reports/coverage_spotcheck.csv`（覆盖率抽查材料）

## 验收口径（tasks.md）

FAIL 率 <10%、citation_coverage ≥0.8、无格式类重试触发、中际旭创技术类期次错位 FAIL 13→0。

## 第一轮（修复前，HEAD `c76cc21`）

| 标的 | 终态 | FAIL 率 | 桶分布 | coverage |
|---|---|---|---|---|
| 汉森制药 002412 | failed* | 9/37 = 24.3% ❌ | semantic_term ×9 | 0.5778 ❌ |
| 贵州茅台 600519 | completed | 10/60 = 16.7% ❌ | semantic_term ×9 + semantic_period ×1 | 0.7209 ❌ |
| 中际旭创 300308 | completed | 9/60 = 15.0% ❌ | semantic_term ×9（**期次错位 0** ✓） | 0.7692 ❌ |

\* 汉森 session failed 发生在 Layer IV 风控辩论之后（risk_judge/fund_manager 段），与本 delta 改动面无交叠（辩论/决策层未触碰），茅台/中际旭创同代码路径 completed，判定为瞬态故障；修复后复跑 completed。

**根因分析**（后端日志 + Langfuse trace 双查）：28 条 FAIL 中 27 条为同一误报类——`semantic_term_mismatch` 桶对「词表外 metric_name」（已申报但词表无规范键）判 FAIL，而 state 指标段空间开放（报表行名/dupont L3/health_score/garp），词表不可闭合，LLM 申报的自然名（营业收入增长率/销售费用率/货币资金/健康度评分等）全部中弹。另发现 1 条 alias 冲突：`net_profit` 挂在「净利润」下，而 `quarterly_trend.net_profit` 实为归母净利润序列。词表内真正张冠李戴 0 条。

## 修复（commit `d42b60d`）

- **D5 扩展**：词表外 metric_name → 跳过术语检查、计覆盖缺口，不判 FAIL（spec delta 补「词表外术语显式降级」场景；rejudge 离线镜像同步；T3 旧语义测试 `test_unknown_term_fails` 按新口径改写）
- **alias 修复**：`net_profit` 移至「归母净利润」canonical；`yoy` 补自然申报名（净利润同比增速/归母净利润同比/营收同比）
- **prompt 规则**：三数据型分析师 prompt 补「词表外/不确定置 null（计缺口不判 FAIL，严禁编造）」；fundamental 补「growth_rates.* 填基指标名，勿带增长率/同比后缀」「quarterly_trend.yoy/qoq 填 同比/环比」；契约测试钉死
- v1.1 门禁复跑仍全过（semantic 检出率 1.0——v1.1 构造用词表内错位，不受降级影响）

## 第二轮（修复后，HEAD `d42b60d` + prompt 已重发布）

| 标的 | 终态 | FAIL 率 | coverage | 重试 | 判定 |
|---|---|---|---|---|---|
| 汉森制药 | completed | 1/29 = **3.5%** ✅ | 0.6957 ❌ | 无 | FAIL 为真阳性（FCF vs FCF收益率 张冠李戴，词表内拦截正确） |
| 贵州茅台 | completed | 0/33 = **0%** ✅ | 0.6296 ❌ | 无 | — |
| 中际旭创 | completed | 0/37 = **0%** ✅ | **0.8333** ✅（重试后二次上报） | fundamental_analyst ×1 | **定向重试实证**：首轮 value_mismatch → 单分析师重跑 → 全 PASS；格式类桶零触发 ✅ |

- **期次错位 13→0** ✅（三标的均无 semantic_period_mismatch 技术类 FAIL）
- **无格式类重试触发** ✅（唯一一次重试由 value_mismatch 触发，符合分桶设计）
- **FAIL 率 <10%** ✅（三标的 3.5%/0%/0%）
- **coverage ≥0.8**：中际旭创达标（0.8333），汉森/茅台未达标（0.70/0.63）⚠️ 见下

## coverage 未达标归因（机器预分类，人工终裁材料：`reports/coverage_spotcheck.csv`）

修复后三标的 unmatched 共 20 条（汉森 7 / 茅台 10 / 中际旭创 3，按重试后最终 score 计）：

- **scale_miss（真实逃逸，设计要暴露的）约 12 条**：正文评论性数字无 claim 认领（如 茅台「1400亿/1169元/969元/-52%/20%/30%」、汉森「73.22%/96.6%/21.93%」）。这正是普查的召回压力目标——是否要求 LLM 对评论性数字也建档，属口径决策。
- **sign_mismatch 2 条**：正文「下滑10.05%」vs stated -10.05，量级可追溯但符号相反，认领口径为符号敏感。改符号不敏感可认领，但符号恰是方向词检查兜底的内容。
- **rounded 约 6 条**：2% 内约数（如 91.93% vs 91.9% 级差异），口径可接受度待定。

**待用户决策**：① 接受实测区间（0.63–0.83）并调整冒烟门槛/告警阈值措辞（spec 变更）；② 强化 prompt 覆盖纪律后再验；③ 放宽认领口径（符号不敏感/约数容差）。本报告不擅自变更 spec 阈值。

## 遗留观察

- Langfuse trace 的 span 级观测不完整（observations 仅到 fetch 段），score/metadata 完整；verify_citations span 取证依赖 score 时序而非 span metadata。
- 冒烟脚本已修「同名 score 取时间戳最新」（重试二次上报场景）。

---

## 附录 A：20 条抽查人工终裁（2026-09-02 追加）

**裁决人**：用户逐条对照 `reports/coverage_spotcheck.csv` 的 `source_sentence` 复核。
**材料**：`reports/coverage_spotcheck.csv`（v2，含 trace_id/出处原句/最近 claim 偏差/机制分类；human_verdict 已回填，另附 note 列）。

### 7 类重分类（替代机器初分类）

| 类 | 条目 | 实质 | 裁决 |
|---|---|---|---|
| A 普查误报 | 20%（仓位档位脚手架）、15%（辩论机会成本估计） | 正则把 prompt 模板/主观估计当事实数字 | accept + 修普查（排除模板文本、估计语境豁免） |
| B state 有、没建 claim | -368%、-52%、-15.2%（state anomalies/红灯项原样输出） | 纯纪律失败，可校验数字裸奔 | reject → 确定性补 claim |
| C 比较基期裸奔 | 21.93%、73.22%、17.48%（2024 基期值） | comparative claim 只建当期值 | reject → 启用 field_ref_b 补基期 |
| D 计算值未申报 | 96.6%（FCF 同比） | computational claim 缺失 | reject → 补 computational claim |
| E 约数/重述 | 91.93%、-4.5%、108%、21.67%、30%（ROE 超 30% 阈值式复述） | 同一指标口头约数 | accept（普查容差放宽 2%、不等式匹配） |
| F 符号问题 | 10.05%、33.5%（方向词已表达） | 符号敏感 | accept（方向词符号不敏感匹配） |
| G 事件数字 | 969元、1169元（新闻"出厂价由969上调"） | 事件溯源内容 | exempt（事件豁免/白名单，正文注明来源） |

**1400 亿改判**：机器初判"value_mismatch 疑错"，人工复核出处原句为"账上货币资金+拆出资金合计超过1400亿元"——**非营收，是货币资金口径**，数字正确但未建 claim → 裁决 reject（去 balance_sheet 验并补 claim），非"疑似错误"。

**75.85%**：无出处原句（未随 trace 落库），毛利率 77.36 差 2.0%，介于约数与错值之间 → needs_review（单独复核原句）。

### 关键事实

- **20 条中无一条是编造的错数字**——真正的幻觉召回压力目标（错且无人拦）在这批样本中为 0，与"真实幻觉≈0"的既有结论一致；coverage 工具抓到的主要是**纪律缺口（B/C/D）与普查自身噪声（A/F/E）**。
- 机器初分类（value_mismatch/scale_miss 等）在"值不一致"上偏机械，会误报指标张冠李戴（1400亿 即例证）；人工按出处原句复核是必要环节。

### 后续（另建 issue 跟踪，不在本 change 归档范围）

1. 普查脚本 v3：排除模板/脚手架文本、方向词符号不敏感、容差 0.5%→2%、"超/约/近 X"不等式匹配；
2. B 类：state anomalies 确定性自动补 claim（键名+数值都在 state，纯代码兜底）；
3. C/D 类：产出后校验 + field_ref_b 双端建档落地；
4. G 类：事件数字豁免纪律（匹配 event store 标记 event_covered）。
