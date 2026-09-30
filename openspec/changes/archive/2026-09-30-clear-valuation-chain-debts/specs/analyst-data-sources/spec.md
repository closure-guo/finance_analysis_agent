# Delta for analyst-data-sources

## ADDED Requirements

### Requirement: 同业财务数据获取

系统 SHALL 实现同业财务数据抓取（`AKShareClient.fetch_peer_data(stock_codes)`）：对用户指定的对标股代码列表逐标的获取名称、PE、PB。实现 SHALL 复用 `fetch_stock_quote` 的主源/回退链（东财 → 百度估值+腾讯）以继承其单位归一与降级语义。单标的抓取失败 SHALL 跳过该标的且不拖垮整批；全部标的失败或输入为空 SHALL 返回 None（fetch 层既有 optional 降级语义）。返回值 SHALL 为 DataFrame 且列名与相对估值消费契约一致（name/PE/PB）。市场平均 PE（`state.industry_pe`）与同业个股 PE 是不同口径的数据源，两者 SHALL 并存可辨。

#### Scenario: 有对标股时返回同业 DataFrame

- GIVEN 用户请求携带 peer_codes="688012,002371" 且行情源可达
- WHEN fetch_data 执行同业抓取
- THEN `state.peer_financials` SHALL 为 DataFrame
- AND 列 SHALL 含 name/PE/PB，每行对应一个成功抓取的对标股
- AND 相对估值（relative_valuation）SHALL 以该数据计算

#### Scenario: 单标的失败跳过不拖垮整批

- GIVEN peer_codes 含两个代码，其一行情全源失败
- WHEN 同业抓取执行
- THEN 结果 SHALL 仅含成功标的的行，SHALL NOT 抛异常
- AND 相对估值 SHALL 基于剩余同业计算

#### Scenario: 全部失败降级 None

- GIVEN 全部对标股行情抓取失败
- WHEN fetch_data 完成
- THEN `peer_financials` SHALL 为 None（与既有 optional 降级同语义）
- AND 管线 SHALL 继续执行，相对估值段以缺失声明呈现

#### Scenario: 未指定对标股时不抓取

- GIVEN 请求未携带 peer_codes
- WHEN fetch_data 执行
- THEN SHALL NOT 触发同业抓取调用
- AND `peer_financials` 保持 None
