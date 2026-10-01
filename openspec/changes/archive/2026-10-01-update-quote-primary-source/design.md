# Design: update-quote-primary-source

## Approach

### 1. 腾讯单标的直查（新主源）

akshare 无可用的单标的腾讯行情 wrapper（`stock_zh_a_spot_tx` 亦是全市场翻页，约 28 页/次，不可采用）——在 `akshare_client.py` 新增 `_fetch_tencent_quote(symbol)`，直接 `requests.get("https://qt.gtimg.cn/q={symbol}")`（`_to_sina_symbol` 前缀复用，如 `688072`→`sh688072`），GBK 解码后按 `~` 分割。该模块已有东财/百度/腾讯多源直查与降级先例，layer 归属不变。

**实测字段映射基线（2026-10-01，sh688072）**——实现与单测以本表为准：

| 串位 | 字段 | 值（拓荆样本） | 映射与归一 |
|---|---|---|---|
| 3 | 最新价 | 640.00 | `price`（元） |
| 32/33 | 涨跌/涨跌% | -16.68/-2.54 | `change`/`change_pct` |
| 34/35 | 最高/最低 | 675.00/635.73 | `high`/`low` |
| 38 | 换手率 | 1.19 | `turnover_rate` |
| 39 | 市盈率 | 85.97 | **不消费**（TTM 口径，见裁决 2） |
| 44 | 流通市值 | 1818.80 | `float_market_cap`，亿 ×1e8 → 元 |
| 45 | 总市值 | 1869.91 | `market_cap`，亿 ×1e8 → 元 |
| 46 | 市净率 | 14.55 | `PB` |

字段位以解析结果与金样本断言钉死，不写「第 N 位」魔法数进业务逻辑（解析层维护位序常量表，字段缺失/串变形 → 返回 None 触发回退）。

### 2. 两项口径裁决（任务内用金样本复核后落单测）

1. **market_cap 单位**：腾讯总市值单位=亿（1869.91 与本日披露节/百度双源一致）。fetch 层 ×1e8 归一到元，与 C1 修复后的统一元契约及 compute 元→亿单点换算对齐。**金样本**：sh688072 → market_cap=186991000000±容差；与百度同源日核对偏差 <0.5%。
2. **PB 双源口径差**：腾讯 14.55 vs 百度 14.71（≈1%，净资产快照口径不同）。裁决：**主源命中时以主源为准，不做跨源融合**；双源形单测钉死两个输出各自的期望值（同一测试夹具分别断言 tencent/baidu 路径），差异本身登记进 metrics.md §1 备注。MUST NOT 在 quote 层做跨源挑选或平均。
3. **腾讯 PE 不消费**：实测 85.97 ≈ 我们 derived_ttm 85.93，证明其为 TTM 口径。quote 层消费它将引入「外部 TTM 冒充主源静态 PE」的口径污染，违反 valuation-signal-integrity「static=主源 / derived_ttm=TTM 推导」可辨性。裁决：quote 不输出 PE 键 → compute 走既有 `PE_missing → derived_ttm` 路径（本变更后生产恒为 derived_ttm 口径），GARP/相对估值/上下文注入行为零变化。腾讯 PE 值可在观测面（日志）留存作交叉核对，不入契约。

### 3. 回退链与请求量治理

```
fetch_stock_quote / fetch_peer_data 共用:
  1. _fetch_tencent_quote   主源   1 req/标的
  2. stock_zh_a_spot_em     回退1  全市场翻页（仅主源失败时；fetch_peer_data 保留共享单次 spot 表优化）
  3. 百度估值+腾讯日线       回退2  现状保留
  4. 仅名称                  保底
```

东财 spot 代码路径整体保留（`_quote_from_spot_df`、market_cap 元归一、C1 双源形单测），仅调用时机从「每 quote 必发」降为「主源失败才发」——封禁期自动全量走主源/第二回退，解封期请求量有界。**根治点是主源不再是翻页**，而非删除东财（删除会丢掉解封期一个可用的回退源，与 data-source-resilience 既有「多级回退」能力取向一致）。

### 4. incident 033 终审 C1 保留意见重新定性

原保留意见「merge 后首次东财可用 run 须抽验主源 static PE 路径量级」基于东财为 quote 主源的前提。本变更后东财降为回退，且腾讯无静态 PE——生产路径中 static 口径 PE 恒缺失，derived_ttm 成常态（GARP 静态口径比较随之恒入缺失桶，行为可预期且诚实）。C1 保留意见改写为：**「东财回退路径解封后，于任一实跑中抽验一次东财回退分支的 market_cap 量级与 sources_seen 标注」**——回退代码与双源形单测继续生效，抽验降级为一次性回归确认。落 `docs/incidents/033` 状态段与本 delta 人工验证报告。

### 5. 连锁面（不改动但需登记）

- `valuation-signal-integrity` spec 无需修改：其 Scenario「主源 PE 存在时不覆盖」是条件式（IF quote 携带 PE），主源不携带时天然走推导路径，契约自洽。
- `data-source-monitoring` spec 不契约化 source 标签枚举，`sources_seen` 增加 `tencent` bucket 是代码层扩展，无需 delta。
- 同 IP 风险外溢（解禁/新闻/研报/季度利润表等东财非行情域）不阻断本变更，登记为数据源监控观测项；若扩散再立项评估 Tushare 补基本面（T-1 语义仅适合非行情数据）。
- 披露节/引用面：quote 输出 dict 键集不变，citation 源路径（`quote.market_cap` 等）不变，无 citation delta。

## Alternatives Considered

- **雪球单标的接口（stock_individual_spot_xq）**：字段全但依赖雪球 cookie/token 生命周期管理，第三方登录态依赖与东财封禁同病（社区先例：cookie 方案失效快）。不选。
- **Tushare Pro 作主源**：daily_basic 有 PE/PB/市值但 T-1，决策完整性门禁的现价交叉校验与技术面现价引用需要当日价。留作基本面补位候补，不作行情主源。
- **直接删除东财 spot 路径**：请求量根治更彻底，但丢掉解封期回退源、C1 修复与单测资产报废。降级保留优于删除。
- **pytdx/掘金终端**：协议逆向维护停滞 / 终端常驻登录的运维负担，为一个 quote 接口引入不值。

## Risks

- **腾讯接口无 SLA、字段位序无契约**（对策：解析层位序常量表 + 金样本单测 + 串变形返回 None 即回退，风险等价于既有百度回退）
- **PB 双源口径差引发下游结论小幅漂移**（对策：同业均值/相对估值结论对 1% 级 PB 差异不敏感；metrics.md §1 登记切点，eval 对照期标注数据源切换时间）
- **腾讯也被东财式反爬波及的长期风险**（对策：三级回退链本身即缓释；若腾讯也失效则东财大概率已解封——两源同封概率低，且回退2完整保留）
- **封禁期全量走腾讯造成的请求集中**（对策：单标的 1 请求/标的 + fetch_peer_data 复用逐标的调用，日批 5 任务量级 ~30 req/日，远低于触发线）
