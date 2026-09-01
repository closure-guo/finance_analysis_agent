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
