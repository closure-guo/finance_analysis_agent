# Tasks: update-track-record-settle-price-display

- [x] 列表页：结算入场价（后复权）列 + 参考价/结算价口径列头标注，进行中行未结算占位；行类型补 `settle_entry_price` 字段；单测覆盖（已结算行三价/进行中行占位/列头文案）
- [x] 详情页：价格区三格（参考价盘面/结算入场价后复权/结算价后复权）+ 口径标注；单测覆盖
- [x] E2E：track-record 套件加「已结算行同口径价格展示」用例（seed 带 settle_entry_price 的 resolved 观点），三套件门禁全绿
- [x] 人工验证报告落 `tests/validation/`
