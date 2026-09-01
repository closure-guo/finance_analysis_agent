# Tasks: harden-citation-semantic-coverage

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出。
> 回填（2026-09-01）：代码任务 T1-T13 全部完成（分支 feat/harden-citation-semantic-coverage，13d38d4..5b775a6，逐任务 SDD 审查通过 + 终审 APPROVED）；剩余未勾项均为 live/人工门禁，archive 前置。

## 前置

- [ ] 人工 ADR 落地：重试路由按桶分流（行为变更）、`citation_coverage` 阈值默认值（live 遗留 1：ADR 人工维护，agent 不得新建）
- [x] 确认契约修复（负索引/英文键/相对容差）已合入且 verifier-baseline-v1 已冻结（bd25a5b 已合入；κ=0.934 已冻结）

## 验收项

### context 语义声明（修期次错位）

- [x] context 构建为每个序列数据块注入机器生成语义头（方向 + 最新期语义 + 期数），覆盖 technical / macro / fundamental 全部序列（T8，4c81415；`_series_semantic_header` 机生注入三构建器，tests/nodes/test_analysts.py 钉死）
- [ ] 复现测试：中际旭创场景重跑，技术类期次错位 FAIL 清零（13 条 → 0）（live 遗留 3：三标的冒烟）

### Claim schema 与术语/期次一致性

- [x] Claim 增加 `metric_name`（枚举，含中文别名映射）与 `period`，default None 兼容旧数据（T1+T2，90a9d75/358eff9；metric_vocab 词表 + Claim 扩字段，default None）
- [x] 校验器新规则：metric_name 规范键 == field_ref 末端键，不一致判 FAIL（桶：semantic_term_mismatch）；period 与 field_ref 期间段不一致同理（T3，4d1e10d + 4556816 macro/quarterly 索引期次解析修复）
- [x] 新字段为 None 时跳过检查并计覆盖缺口，不静默 PASS（D5 显式降级；终审修复 5b775a6：回声/方向提前 FAIL 也保留缺口标记）

### claim 内部一致性

- [x] stated_value 归一化后在 interpretation 中可匹配（"约 45%"/"45.2%" 口径 fixture 钉死），不可匹配判 FAIL（桶：internal_inconsistency）（T4，cd81a36 + 40621ba 误报双修复；汉森钉死测试残量 5/5 回归）
- [x] 方向词检查：interpretation 含增长/下降类词且与 delta 符号矛盾 → FAIL（同桶）（T4；范围收窄至增长类防误报，`_is_growth_claim` 钉死）

### 正文覆盖率

- [x] markdown 数字普查（归一化 + 豁免清单），产出 `citation_coverage` 并上报 Langfuse（NUMERIC，不进路由，<0.8 告警）（T5+T6，33d0bf6/6cb0071；<0.8 时 warning + span 标记，不进路由）
- [ ] 归一化与豁免规则 fixture 测试 ≥15 例（已达成 22 例，tests/test_citation_coverage.py）；首批产出人工抽查 20 条确认口径（live 遗留 4）

### 重试分流

- [x] after_citation 路由按桶分流：仅 value_mismatch 触发定向重试（单分析师 Send 派发 + 失败明细上下文），其余桶直判（T6+T7，f92312f；`citation_retry_targets` 过滤 Send + `citation_retry_feedback` 注入）
- [x] 重试上限 3 不变；重跑后该分析师 claim 全部重新校验；iteration_count 语义不回归（T7；tests/test_routing.py 路由测试全绿，停滞降级 0.8 因子语义不变）

### evaluation 扩展

- [x] 基准集 v1.1：near_miss 改 ±{0.3,0.5,0.7,1}% 四档且 50% 为 should_pass（容差内）样本；新增 semantic_mismatch 子集（术语/期次张冠李戴，数值正确）（T10，920d323；真实 v1 数据实证 50% 配额）
- [x] run_experiment 指标增加 `citation_coverage`；decision_grounding judge rubric 增加 interpretation 语义核对项，rubric 版本号递增（T12 d0ea90c：citation_pass/citation_coverage + 均值 CI；T13 36dae73：RUBRIC_VERSIONS decision_grounding=3 + 语义核对条款）
- [ ] 全部合入后重跑 measure.py，冻结 verifier-baseline-v1.1（含 semantic_mismatch 子集检出率披露）（live 遗留 5：build_v11 生成 + measure.py 重跑 + results/v1.1.md 冻结）

### 通用

- [x] `uv run pytest` 全过、`uv run ruff check`、`uv run mypy`（本任务范围）零错误（1663 passed / 2 skipped；4 failed 均为预存 @live 网络测试，本分支未触碰；ruff 全绿；mypy 本分支文件零错误，另修复 evals/run.py 预存 3.12 兼容错误）
- [ ] 三标的冒烟（汉森制药/贵州茅台/中际旭创）：FAIL 率 <10%、coverage ≥0.8、无格式类重试触发（live 遗留 3）

## Live 遗留（archive 前置人工门禁）

1. 人工 ADR（`docs/adr/`）：重试按桶分流 + `citation_coverage` 0.8 阈值默认值
2. prompt 发布：`uv run python scripts/deploy_prompts.py`（T9 改了 4 个分析师 prompt，未发布则 eval 门禁拒绝运行）
3. 三标的冒烟：汉森/茅台/中际旭创（FAIL<10%、coverage≥0.8、期次错位 13→0）
4. 覆盖率抽查：首批产出人工抽查 20 条确认普查口径
5. 基准集冻结：`build_v11.py` 生成 → `measure.py --labeled data/benchmark_v11.jsonl` 重跑 → results/v1.1.md 冻结 verifier-baseline-v1.1
6. judge 重校准：rubric v3 按 Judge 校准门禁重校准（人工一致性 ≥80%）后上线
