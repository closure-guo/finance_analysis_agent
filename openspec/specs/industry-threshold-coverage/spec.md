# industry-threshold-coverage Specification

## Purpose
由 delta update-financial-freshness-and-valuation 归档建立（2026-09-29 实施完毕并通过独立终审）。
## Requirements
### Requirement: 行业阈值覆盖机制

红黄绿灯阈值 SHALL 支持「行业覆盖优先于通用阈值」：以行业名称子串模糊匹配 `INDUSTRY_OVERRIDES`（现有白酒/酿酒条目为此机制既有实例），命中的指标用行业阈值评灯，未命中的指标沿用通用阈值。新增行业覆盖条目 SHALL 附校准依据（同行业代表公司指标分布的量化说明），MUST NOT 拍脑袋取值。

#### Scenario: 命中行业覆盖的指标改用行业阈值

- GIVEN 个股行业名称含「半导体设备」且覆盖表含该键的存货周转率阈值
- WHEN 红黄绿灯评判存货周转率
- THEN SHALL 用半导体设备阈值评灯，MUST NOT 用通用阈值 (5, 2)

#### Scenario: 未命中指标沿用通用阈值

- GIVEN 个股行业名称含「半导体设备」但覆盖表无 ROE 条目
- WHEN 评判 ROE
- THEN SHALL 用通用 ROE 阈值评灯

### Requirement: 半导体设备行业首批覆盖

系统 SHALL 为半导体设备行业（行业名称子串「半导体设备」）提供首批阈值覆盖，至少覆盖：存货周转率、速动比率、应付账款周转率。覆盖依据：设备商收入按客户验收确认、存货中大比例为已发货待验收设备、负债中合同负债（客户预付款）占比高，通用制造业阈值系统性误判为红灯。具体取值见 change design.md 的校准论证。

#### Scenario: 拓荆科技存货周转率不再误判红灯

- GIVEN 拓荆科技(688072) 行业为半导体设备、年报口径存货周转率 0.56
- WHEN 红黄绿灯按行业覆盖阈值评判
- THEN 存货周转率 SHALL NOT 评红灯（按 design.md 校准值落在绿或黄区间）

#### Scenario: 健康度评分随覆盖阈值重算

- GIVEN 同一股票在行业覆盖前后各评一次健康度
- WHEN 覆盖生效
- THEN 健康度评分 SHALL 按覆盖后灯色重算
- AND 评分变化可由阈值覆盖解释（不引入其他变量）

### Requirement: 健康度评分行业口径披露

当行业阈值覆盖生效于任一评灯指标时，红黄绿灯与健康度评分输出 SHALL 携带 `industry_override` 标注（行业名 + 覆盖指标清单），报告渲染层 SHALL 使读者可见评分所用口径；无覆盖时输出 SHALL 标注通用口径。

#### Scenario: 覆盖生效时评分携带口径标注

- GIVEN 拓荆科技健康度评分计算完成且存货周转率经行业覆盖评灯
- WHEN 评分结果写入 state
- THEN 结果 SHALL 含 `industry_override`（行业「半导体设备」、覆盖指标含存货周转率）
- AND 报告健康度章节 SHALL 展示该口径标注

#### Scenario: 无覆盖时标注通用口径

- GIVEN 贵州茅台行业为白酒、存货周转率命中白酒覆盖
- WHEN 健康度评分输出
- THEN `industry_override` SHALL 记录白酒覆盖（现有行为显式化）
