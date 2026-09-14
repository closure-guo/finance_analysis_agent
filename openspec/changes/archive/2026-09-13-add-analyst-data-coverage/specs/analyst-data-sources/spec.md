# Delta for analyst-data-sources

## ADDED Requirements

### Requirement: 公告与研报数据获取

系统 SHALL 在深度分析数据准备阶段并行获取个股公告列表（巨潮 cninfo，近 180 天，含标题/类别/日期）与券商研报列表（东财，含标题/机构/评级/目标价/日期），失败或空结果 SHALL 降级为空列表且不阻断管线。

#### Scenario: 公告与研报正常装配

- GIVEN 深度分析管线进入数据准备阶段
- WHEN 巨潮与东财接口可用
- THEN state SHALL 包含 announcements 与 research_reports 键
- AND 数据 SHALL 写入缓存（TTL 3600s）

#### Scenario: 接口失败降级

- GIVEN 公告或研报接口调用失败
- WHEN 数据准备完成
- THEN 对应 state 键 SHALL 为空列表
- AND 管线 SHALL 继续执行不中断

### Requirement: 解禁与大宗交易数据获取

系统 SHALL 获取个股限售解禁排队（东财，含解禁日期/数量/市值）与近 30 天大宗交易明细（东财按日期区间拉取后按个股过滤，含成交价/溢价率/买卖营业部），失败降级为空列表。

#### Scenario: 解禁与大宗装配

- GIVEN 深度分析管线进入数据准备阶段
- WHEN 东财解禁/大宗接口可用
- THEN state SHALL 包含 share_unlock 与 block_trades 键

### Requirement: 分析师消费新信源

基本面分析师的上下文 SHALL 包含公告列表（标题/类别/日期）与研报列表（标题/机构/评级/目标价/日期），prompt SHALL 附防锚定条款（研报评级/目标价是卖方观点，不得直接作为结论依据）；舆情分析师的上下文 SHALL 包含解禁与大宗事件面。

#### Scenario: 基本面上下文含公告与研报

- GIVEN state 含非空 announcements 与 research_reports
- WHEN 基本面分析师构建上下文
- THEN 上下文 SHALL 含公告标题与研报评级/目标价段落
- AND 研报段落 SHALL 附防锚定提示

#### Scenario: 舆情上下文含事件面

- GIVEN state 含非空 share_unlock 或 block_trades
- WHEN 舆情分析师构建上下文
- THEN 上下文 SHALL 含解禁/大宗事件段落

### Requirement: 新信源 claim 纳入回声匹配

citation 校验器 SHALL 将 announcements/research_reports/share_unlock/block_trades 的标题字段纳入文本 claim 回声匹配源集合（与 news_list/key_events 同语义：归一子串命中即 PASS(echo)，未命中 UNVERIFIABLE(text)）。

#### Scenario: 公告标题 claim 回声命中

- GIVEN 分析师 claim 引用 announcements 信源且 stated 内容为某公告标题
- WHEN citation 校验器执行文本回声匹配
- THEN 命中 SHALL 判 PASS(echo)
