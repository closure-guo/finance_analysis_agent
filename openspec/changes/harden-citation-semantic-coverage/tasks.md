# Tasks: harden-citation-semantic-coverage

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出。

## 前置

- [ ] 人工 ADR 落地：重试路由按桶分流（行为变更）、`citation_coverage` 阈值默认值
- [ ] 确认契约修复（负索引/英文键/相对容差）已合入且 verifier-baseline-v1 已冻结

## 验收项

### context 语义声明（修期次错位）

- [ ] context 构建为每个序列数据块注入机器生成语义头（方向 + 最新期语义 + 期数），覆盖 technical / macro / fundamental 全部序列
- [ ] 复现测试：中际旭创场景重跑，技术类期次错位 FAIL 清零（13 条 → 0）

### Claim schema 与术语/期次一致性

- [ ] Claim 增加 `metric_name`（枚举，含中文别名映射）与 `period`，default None 兼容旧数据
- [ ] 校验器新规则：metric_name 规范键 == field_ref 末端键，不一致判 FAIL（桶：semantic_term_mismatch）；period 与 field_ref 期间段不一致同理
- [ ] 新字段为 None 时跳过检查并计覆盖缺口，不静默 PASS

### claim 内部一致性

- [ ] stated_value 归一化后在 interpretation 中可匹配（"约 45%"/"45.2%" 口径 fixture 钉死），不可匹配判 FAIL（桶：internal_inconsistency）
- [ ] 方向词检查：interpretation 含增长/下降类词且与 delta 符号矛盾 → FAIL（同桶）

### 正文覆盖率

- [ ] markdown 数字普查（归一化 + 豁免清单），产出 `citation_coverage` 并上报 Langfuse（NUMERIC，不进路由，<0.8 告警）
- [ ] 归一化与豁免规则 fixture 测试 ≥15 例；首批产出人工抽查 20 条确认口径

### 重试分流

- [ ] after_citation 路由按桶分流：仅 value_mismatch 触发定向重试（单分析师 Send 派发 + 失败明细上下文），其余桶直判
- [ ] 重试上限 3 不变；重跑后该分析师 claim 全部重新校验；iteration_count 语义不回归

### evaluation 扩展

- [ ] 基准集 v1.1：near_miss 改 ±{0.3,0.5,0.7,1}% 四档且 50% 为 should_pass（容差内）样本；新增 semantic_mismatch 子集（术语/期次张冠李戴，数值正确）
- [ ] run_experiment 指标增加 `citation_coverage`；decision_grounding judge rubric 增加 interpretation 语义核对项，rubric 版本号递增
- [ ] 全部合入后重跑 measure.py，冻结 verifier-baseline-v1.1（含 semantic_mismatch 子集检出率披露）

### 通用

- [ ] `uv run pytest` 全过、`uv run ruff check`、`uv run mypy`（本任务范围）零错误
- [ ] 三标的冒烟（汉森制药/贵州茅台/中际旭创）：FAIL 率 <10%、coverage ≥0.8、无格式类重试触发
