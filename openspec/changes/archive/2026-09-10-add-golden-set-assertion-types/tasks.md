# Tasks: add-golden-set-assertion-types

## 1. schema 与样本

- [x] 1.1 `evals/golden/schema.py`：GoldenEntry（as_of_date/origin 缺失拒绝、rule_derived 仅 pilot、llm_judge 必带校准元数据）
- [x] 1.2 首批样本 10 条：T8 事故回归 `g-fin-0001-0004`（incidents 001 三条 + 020 校验器误杀一条，self-contained ground_truth）+ T6 拒答 `g-fin-0101-0103` + T8 合规 `g-fin-0201-0203`

## 2. deterministic 判定器

- [x] 2.1 `evals/golden/gates.py`：`judge_t6_refusal`（不可得声明 + 逃逸数字扫描）、`judge_t8_compliance`（forbidden/must_contain）、`verify_against_ground_truth`（容差常量唯一来源 import citation）+ 批量 `run_entries`/CLI
- [x] 2.2 注入语义用例（T6 逃逸数字/pass、T8 违规词/缺风险提示/pass）固化为测试——门禁会开火

## 3. v12 身份降级与 CI 接线

- [x] 3.1 `claim_benchmark/measure.py`：输出 `benchmark_identity`（rule_derived + regression_probe + real_accuracy_not_claimed），报告打印「算法回归探针，不构成真实准度声明」
- [x] 3.2 `ci.yml` 新增 `Golden set gate`（零 token deterministic，全 PASS 才绿）

## 4. 标注与 κ

- [x] 4.1 事故回归样本携带人工裁决 verdict（single_human 初标，来自 incidents 定性）——待 double_human 复核后首算真实 κ（标注工具链复用 claim_benchmark 机制）
- [x] 4.2 标注后 κ/F1 写入金标准 meta 供「真实准度声明」（列入下一步标注流程）

## 5. 回归

- [x] 5.1 evals 全量 380 绿（含 golden 13） + ruff clean + `openspec validate --strict` 通过
- [x] 5.2 本机 golden gate 验证：10 样本全 PASS、exit=0；measure 身份声明实测打印