# Tasks: add-prediction-pool-integrity

- [x] 口径预登记先行：`docs/evals/metrics.md` §1.9 增补 IC/ICIR + 敞口对齐蒙特卡洛零模型口径（公式/阈值/样本口径/版本号），先于任何实现代码
- [x] 归属日纯函数：提取/实现 `derive_attribution_date`（与 settle_entry_price 派生同源），单测覆盖收盘前后/非交易日边界
- [x] 日主判定改造：judgment/job 支持日主视图 + `duplicate_of_day` 关闭（superseded 先行），回归测试覆盖同日重跑/同日变更链/跨日正常三场景
- [x] NAV 组合分母切换：盯市组合构成消费日主视图，track-record 指标回归测试更新
- [x] 统计分母切换：胜率/平均超额/回避正确率/样本量仅计日主，口径切点按 versioning 登记分段不混算
- [x] 显著性统计模块：`significance.py` 纯函数（IC 月度序列 / ICIR 门槛 / 蒙特卡洛零模型敞口对齐 + 种子复现），单测覆盖样本不足/期数不足/敞口对齐三红线
- [x] 只读统计端点接入 IC/零模型读数（结论必附分位，点估计单独出现即拒绝）
- [x] 前端观点日志 `duplicate_of_day` 徽标 + track-record E2E 套件加用例（三套件门禁全绿）
- [x] 存量生产库 dry-run 核对：76 条 open 的分类结果人工复核（688072 预期 1 主 + N duplicate），不迁移数据
- [ ] 人工验证报告落 `tests/validation/`，10-08 前部署（净值重启窗口）
