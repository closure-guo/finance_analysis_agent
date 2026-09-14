# Proposal: harden-evaluation-dataset-sampling

## Why

a-share-analysis-v1 dataset 16 条中 follow_up×3 与 clarify×2 在实验里 skipped 虚占（task.py 首版跳过），实际出分 deep 仅 7-8 条；独立标的仅 6 个、行业/市值风格单一（白酒/新能源/银行/半导体大盘蓝筹）；deep 边界语义偏离 spec（应为歧义/ST/次新，现为专项问询）；quick 多条 expected_output 为空 → 零确定性断言。「每次换标的」无机制，固定 16 条反复跑易过拟合。

## What Changes

- dataset_items.json 重构：新增多行业标的（保险/家电/有色/安防/券商）、deep 边界补「分析平安」歧义样本（无代码）、quick 尽量补 `expected.ticker`、follow_up 3→1；所有条目加 `metadata.pool`（baseline / rotating）
- `dataset_seed.py` 支持按 pool 建库 + rotating 按标的组抽样（`--pool baseline|rotating --rotating-sample N --rotating-seed S`，rotating 用独立 dataset 名，跨轮不同 seed 换标的、同 seed 可复现）
- `evals.run` 支持 `--dataset` 参数（默认 a-share-analysis-v1），实验记录所用 dataset 名

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `evaluation`: MODIFIED「评估 Dataset 与覆盖矩阵」——dataset 分固定基线池（跨实验可比）与轮换池（每轮抽取不同标的，防过拟合）；deep 边界 SHALL 含歧义解析样本；出分条目占比作为设计约束；ADDED「轮换池抽样建库」Requirement——rotating 池按标的分组随机抽样、独立 dataset 名、seed 可复现

## Impact

- `evals/dataset_items.json`：内容重构（+rotating 池）
- `evals/dataset_seed.py`：pool 过滤与轮换抽样
- `evals/run.py`：--dataset 参数
- 测试：`tests/evals/test_dataset_seed.py`、`test_run.py`
- 文档：`docs/evals/dataset-baseline.md` 登记新基线（实施后）