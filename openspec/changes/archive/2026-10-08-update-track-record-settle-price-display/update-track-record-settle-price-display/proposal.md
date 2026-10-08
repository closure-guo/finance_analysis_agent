# Proposal: update-track-record-settle-price-display

## Why

战绩页观点日志把「入场价」（`entry_price` 参考价，盘面口径）与「结算价」（`exit_price`，后复权 hfq 口径）并排展示，两列不属于同一价格序列，直接对比产生系统性误读：分红历史越长的股票差距越大（601818 ×2.14、300033 ×13.2、600845 ×15.3），用户实际反馈「差的这么多」。区间收益/超额读数本身自洽（计算两端同为 hfq），纯展示层口径混排。真正可比的结算入场基准 `settle_entry_price`（hfq 归属日收盘）已由列表 API 返回（`SELECT *`）但前端未渲染。

## What Changes

- 观点日志表格新增「结算入场价（后复权）」列，位于入场价与结算价之间：已结算行展示 `settle_entry_price`，进行中行展示未结算占位；该列不参与排序（后端排序白名单不变，零后端改动）
- 列头口径标注：「入场价」→「参考价（盘面）」、「结算价」→「结算价（后复权）」
- 详情页价格区从两格扩为三格：参考价（盘面）/ 结算入场价（后复权）/ 结算价（后复权）
- 明确禁止的修法（不入实现）：将结算价折算回盘面口径展示——复权因子随分红漂移，落库 hfq 值是冻结快照，折算等于制造新口径混排

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `track-record`：战绩页面 requirement 增补结算价格同口径展示（结算入场价列 + 口径列头标注 + 详情页三价）

## Impact

- 前端 `frontend/src/pages/trackRecord/TrackRecordPage.tsx`（COLUMNS + 表体渲染）、`frontend/src/pages/trackRecord/PredictionDetailPage.tsx`（价格区三格）+ 对应单测
- E2E：track-record 套件加「已结算行口径展示」用例（seed 需带 settle_entry_price 的 resolved 观点）
- 后端零改动（列表 API 已返回 `settle_entry_price`；排序白名单不动）
- 不迁移数据、不改动任何计算口径
