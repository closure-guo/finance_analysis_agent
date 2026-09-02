# CI 门禁注入式故障演练验证记录（ci-gate-verify）

**日期**：2026-09-01
**目的**：验证「校验器准度回归 CI 门禁」有效——故意注入容差回归，确认 CI 步骤拦截；还原后确认全绿。
**CI 步骤**（`.github/workflows/ci.yml` lint-and-test job，Unit tests 之后）：

```bash
uv run python evals/claim_benchmark/measure.py \
    --labeled evals/claim_benchmark/data/benchmark_v11.jsonl \
    --gate 0.90 --baseline evals/claim_benchmark/results/v11-measure.json
```

门禁契约（measure.py 新增参数，纯离线、无 Langfuse 依赖）：

- `--gate`（默认 0.90）：整体 F1 阈值，低于即 exit 1；
- `--baseline`：冻结基线 measure JSON，相对基线 F1 退步超过 `--max-regression`（默认 0.02）即 exit 1；
- 既有 semantic_mismatch 检出率 ≥ 0.9 门禁不变。

## 演练前置修复：容差镜像缺陷

首次注入 `citation.py` 内联容差字面量（0.005→0.05）时门禁**未拦截**（F1 仍为 1.0）——
根因：`rejudge.py` 镜像复制了容差常量（`ABS_TOL/REL_TOL`），复判不走 `citation.py`，
生产代码改动无法传导到测量，镜像漂移仅靠钉死测试兜底且存在覆盖盲区。

修复（保持契约语义不变的重构）：

- `citation.py` 提取模块级常量 `ABS_TOL = 0.01` / `REL_TOL = 0.005`，三处内联字面量（计算型、数值型、`value_close`）改用常量；
- `rejudge.py` 删除镜像副本，改为 `from finance_agent.citation import ABS_TOL, REL_TOL`（唯一来源）；
- `build_v11.py` 的标签构造公式不动（v1.1 标签语义已冻结，属基准集而非被测代码）。

## 演练记录

### 注入（单点：`citation.py` `REL_TOL = 0.005` → `0.05`）

```
核心样本 n=70（排除 0）
混淆矩阵: {'tp': 14, 'fp': 0, 'fn': 20, 'tn': 36}
Precision=1.0  Recall=0.4118  F1=0.5833  (95% CI [0.4, 0.7308])
门禁 F1 ≥ 0.9: ❌ 未通过
near_miss 过线检出率: 0.0（20 条过线 FAIL 全部漏检，fn 集中桶 ('numerical','near_miss') ×20）
进程退出码: 1
```

→ CI 步骤变红，合并被阻断。✅

### 还原（`git checkout src/finance_agent/citation.py` 后重放重构）

```
基线比对: F1 1.0 → 1.0（Δ+0.0，容忍退步 ≤ 0.02）: ✅ 通过
F1=1.0  (95% CI [1.0, 1.0])  Accuracy=1.0
门禁 F1 ≥ 0.9: ✅ 通过
semantic_mismatch 检出率: 1.0（门禁 ≥ 0.9: ✅）
进程退出码: 0
```

→ 全绿。✅ 同时 `pytest tests/evals/claim_benchmark/ + 全部 citation/rejudge 测试` 179 passed。

## 结论

门禁对「citation 容差契约回归」这一目标故障类有效：注入即红（exit 1），还原即绿（exit 0）。
门禁覆盖边界诚实披露：基准集只覆盖数值/计算型容差语义与 semantic 术语错配；
prompt 层、解析层（field_ref 路径解析）不在此门禁范围内，仍由钉死测试与 LLM 实验回归覆盖。
