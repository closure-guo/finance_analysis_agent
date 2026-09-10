# Tasks: harden-evaluation-dataset-sampling

## 1. dataset_items.json 重构

- [x] 1.1 新增多行业标的 deep 条目（美的 000333 验证过；rotating 池：中国平安 601318/格力 000651/海康 002415/紫金 601899/中信 600030/工业富联 601138/万华 600309 各含 deep+quick），metadata 标注 `pool: baseline|rotating`
- [x] 1.2 deep 边界补充歧义样本「分析平安」（无代码，expected ticker=601318）
- [x] 1.3 quick 条目尽量补 `expected.ticker`；行业类（银行股）metadata note 标注原因
- [x] 1.4 follow_up 3→1；出分占比 14/17 ≈ 82% ≥80%

## 2. dataset_seed.py 分池与轮换抽样

- [x] 2.1 `load_items(pool=...)` 过滤；`seed(pool=...)` 仅建对应池（TDD）
- [x] 2.2 rotating 模式：按标的分组随机抽样 `--rotating-sample N --rotating-seed S`，独立 dataset 名（`a-share-analysis-v1-rot-<seed>`），幂等 + 可复现（TDD：同 seed 同组合、不同 seed 不同组合、每组 deep+quick 成对）

## 3. evals.run 支持指定 dataset

- [x] 3.1 `--dataset` 参数（默认 `a-share-analysis-v1`），experiment metadata 记录 dataset 名
- [x] 3.2 测试覆盖（test_run.py 27 绿）

## 4. 验证

- [x] 4.1 evals 全量测试 367 绿 + ruff clean + `openspec validate --strict` 通过
- [x] 4.2 真实 seed：baseline 幂等（created 3 / skipped 14）；rotating seed=42→格力/中国平安/紫金、seed=43→格力/海康/中信（组合不同、可复现）