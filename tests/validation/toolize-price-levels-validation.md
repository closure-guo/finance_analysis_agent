# toolize-price-levels 验证报告

- 日期：2026-09-04
- 内容：交易价位工具化（calc_price_levels + trader sanity 校验 + quick 行情快照 + 派生值预生成）

## 自动化验证

- 全套后端 pytest：1939 passed / 0 failed（新增 27 例：价位工具 7、sanity 节点/
  路由/修正 12、quick 快照与派生值注入 8）
- 全套 E2E 门禁（CI 镜像）：21 passed / 7 skipped / 0 failed——stub deep 链路
  实际经过 validate_trade_prices 节点（trader→sanity→risk 路由生效）
- ruff / mypy 全绿；delta 过 strict

## 已实现行为核对

- calc_price_levels：entry_ref/近期高低点/ATR(14)/止损带/目标带/放宽带，数据
  不足 available=false 不伪造
- sanity 校验纯规则：价格关系（long stop<entry<target，short 对称）、entry 距
  现价 ≤15%、放宽带；hold/watch 与价位缺失/levels 不可用时如实跳过
- 三路路由：pass/corrected 前行；首次 fail 携反馈打回 trader（上限 1 次）；
  二次 fail 按工具参考带修正并标 price_level_corrected（报告渲染「价位修正」
  ⚠️ 行，可观测不静默）
- quick search_stock 单候选附现价/涨跌幅快照；缺失如实标注「请勿臆测价格数值」
- 技术面 context 注入派生值表（5/20/60 日涨跌幅、距 250 日高低点回撤/反弹，
  数据不足标注）

## 实施中发现并修复

1. calc_derived_series 未处理 kline=None（compute 场景 kline 可缺失）→ 全 None
   兜底，13 个连级失败归零
2. agent_factory.is_streaming 前案（本 session 早前）已修；本次无新增回归

## 待人工验证

1. 真实 LLM 链路：观察 trader 是否引用 price_levels 参考带（Langfuse trace 的
   trader generation input）以及 sanity 打回/修正是否按预期触发（需 LLM 余额）
2. 修正标注在真实报告中的呈现核对
