# Proposal: update-quote-primary-source

## Why

东财自 2026-09-26 起对本机 IP 实施行情 API 域（push2/push2his）级封禁（实测 python/curl/curl_cffi 浏览器指纹全部断连，伪装无效；官网与 datacenter 域正常），且经查为自身抓取模式所致——`fetch_stock_quote` 主源 `stock_zh_a_spot_em` 全市场翻页约 50+ 请求/次拿单只股票，叠加日批与验证实跑触发频率限制。akshare 社区证实该封禁长期化（官方 fix 无效、cookie 方案一天失效），等待解封不解决结构性问题。

## What Changes

- **quote 主源切换**：`fetch_stock_quote` 主源改为腾讯 `qt.gtimg.cn` 单标的直查（1 请求/标的，含价格/涨跌幅/最高最低/换手率/总市值/流通市值/PB），删除「全市场 spot 翻页拿一只股票」的主源路径
- **东财降级为回退**：东财 `stock_zh_a_spot_em` 从主源降为第二级回退（仅在腾讯失败时触发，请求量有界）；百度估值+腾讯日线回退链保留为第三级
- **新增单标的腾讯行情抓取函数**：`_fetch_tencent_quote`（qt.gtimg.cn 直查 + GBK 解码 + `~` 分隔字段映射），akshare 无单标的腾讯 wrapper（`stock_zh_a_spot_tx` 亦为全市场翻页，不可用）
- **字段单位/口径审计**：腾讯总市值=亿（×1e8 归一到元，与 C1 修复后的统一元契约对齐）；腾讯 PE 字段实测为 TTM 口径而非静态——quote 层不消费（PE 语义依赖财务口径，推导留给 compute 的 derived_ttm 路径，契约不变）；PB 与百度存在口径差（14.55 vs 14.71），以双源形单测钉死
- **`fetch_peer_data` 同步切换**：同业抓取复用新主源链（N 个单请求），共享 spot 表逻辑保留给东财回退路径
- **监控标注扩展**：`sources_seen` 增加 `tencent` 主源标注
- **incident 033 终审 C1 保留意见重新定性**：东财主源 static PE 路径随主源切换在生产中不再默认走到，原「merge 后东财可用 run 抽验」改为「东财回退路径解封后抽验一次」（回退代码与双源形单测保留）
- **同 IP 风险外溢登记**：仍可用的东财域（解禁/新闻/研报/季度利润表）与被封 push2 共享出口 IP，列入数据源监控观测项（不阻断本变更）

## Capabilities

- **Modified Capabilities**:
  - `data-source-resilience`：行情 quote 回退链重排（腾讯单标的主源 → 东财 spot 回退 → 百度+腾讯日线 → 仅名称），新增腾讯单标的主源行为契约与字段单位归一要求
  - `analyst-data-sources`：`fetch_peer_data` 复用链描述更新（主源/回退链定义解耦到 data-source-resilience，不再硬编码「东财 → 百度估值+腾讯」）

## Impact

- `src/finance_agent/data/akshare_client.py`：`fetch_stock_quote` / `_quote_from_spot_df` / `fetch_peer_data` / 新增 `_fetch_tencent_quote`；`sources_seen` 标注
- 无 prompt 改动；无 LLM 层改动；披露节/GARP/相对估值的消费契约不变（quote 输出 dict 键集不变，`PE` 键在腾讯主源下自然缺失，走既有 derived_ttm 路径）
- `docs/evals/metrics.md` §1：数据源口径备注登记（quote 主源切换时间点）
- `docs/incidents/033`：C1 保留意见定性更新
- 缓存：腾讯主源数据进入既有 cache 通道，无 schema 变更
