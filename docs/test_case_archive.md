# 测试用例档案（Test Case Archive）

> 基于 [PRD](PRD.md)、[架构设计](architecture.md)、[领域上下文](../CONTEXT.md) 及 [ADR](adr/) 编写。
> 维护者：开发团队 · 最后更新：2026-07-16
>
> 本档案是测试用例的**规格清单与追溯基线**，描述"测什么、怎么测、为何测"。
> 单次运行的人工验证报告放入 `tests/validation/`，E2E 截图/输出放入 `tests/e2e/`，运行时报告放入 `reports/`。

---

## 一、测试策略与原则

### 1.1 核心原则（源自 PRD §Testing Decisions）

| 原则 | 说明 |
|------|------|
| 只测外部行为 | 给定输入 -> 预期输出，不测实现细节（私有函数/内部变量） |
| 财务计算用已知值验证 | 硬编码手算结果验证，不用 mock 替换 pandas 操作 |
| 真实数据结构 | 使用 `pd.DataFrame`（模拟 AKShare 返回结构），不伪造中间结果 |
| 分层隔离 | 纯函数单元测试稳定不 flaky；依赖 LLM/外部服务的放到集成/E2E |

### 1.2 分层测试金字塔

```
            ┌──────────┐
            │   E2E    │  真实链路：前端 Playwright -> FastAPI -> LangGraph -> 真实 LLM + AKShare
            │  (少而重) │  禁止 mock，禁止单测后端 API
            └────┬─────┘
        ┌────────┴────────┐
        │     集成测试      │  节点编排 + 路由 + 会话存储 + 导出（mock 边界：LLM / AKShare）
        │   (中等数量)      │
        └────────┬────────┘
     ┌───────────┴───────────┐
     │       单元测试          │  metrics/ 纯函数 + citation + routing + models + nlp 解析
     │   (多而快，CI 门禁)     │  零 I/O、零 LLM、毫秒级
     └───────────────────────┘
```

### 1.3 三条硬约束（项目规则）

1. **E2E 禁止 mock 数据**：必须使用真实服务（FastAPI + Vite + 真实文件系统）+ 真实输入（可来自 `tests/fixtures/`）。需要打桩的场景下沉到单元/集成测试。
2. **E2E 必须走前端**：通过 Playwright 模拟用户在页面的真实操作（输入/点击/等待渲染），禁止单独用 `requests`/`httpx` 直调后端 API（那属于集成测试）。
3. **测试产物归位**：fixtures -> `tests/fixtures/`、验证脚本 -> `tests/scripts/`、验证报告 -> `tests/validation/`、E2E 输出 -> `tests/e2e/`、运行时报告 -> `reports/`。禁止在根目录新建目录。

---

## 二、测试环境与数据策略

### 2.1 环境矩阵

| 层级 | 运行环境 | 依赖 | 触发方式 |
|------|---------|------|---------|
| 单元测试 | 本地 / CI | 无外部依赖 | `uv run pytest tests/metrics tests/test_citation.py tests/test_routing.py` |
| 集成测试 | 本地 / CI | mock LLM + mock AKShare client | `uv run pytest tests/nodes tests/test_graph_5layer.py` |
| E2E 测试 | 本地（需 Docker） | 真实 LLM API Key + Docker 全栈 | `python tests/e2e/<script>.py` 或 `uv run pytest tests/e2e/test_*.py -s` |

### 2.2 共享 fixtures（`tests/conftest.py`）

提供手算可验证的合成财报数据，所有 metrics 单元测试复用：

| fixture | 内容 | 手算基准（2024） |
|---------|------|-----------------|
| `balance_sheet` | 3 年资产负债表 | 资产=1000, 负债=400, 权益=600 |
| `income_statement` | 3 年利润表 | 营收=1000, 净利润=170, 利润总额=200 |
| `cash_flow` | 3 年现金流量表 | OCF=250, ICF=-100, FCF=-30 |
| `indicators` | AKShare 预计算指标 | 毛利率=40%, 加权 ROE=28.33% |

> 真实标的快照放 `tests/fixtures/`（如 `600519_metrics_raw.json`），用于回归对照。

### 2.3 LLM 依赖处理

- **单元/集成测试**：mock `LLMClient`，验证节点编排逻辑（State 读写、降级、重试），不验证 LLM 输出质量。
- **E2E 测试**：真实 LLM（`LLM_API_KEY` / `DEEPSEEK_API_KEY`），验证完整链路与输出形态。无 Key 时通过 `pytest.mark.skipif` 跳过。
- **质量评估**：LLM 主观质量走 Langfuse Score（L1 LLM-as-Judge），不进 CI 断言（避免 LLM 幻觉污染测试）。

---

## 三、单元测试用例

### 3.1 metrics/ 指标计算（重点，9 个模块）

> 纯函数、无 I/O、无 LLM。财务计算正确性是系统地基。阈值边界必覆盖（红黄绿灯切换点）。

#### 3.1.1 `metrics/validate.py` — 勾稽校验 4 规则

| 用例 ID | 场景 | 输入要点 | 预期 | 现状 |
|---------|------|---------|------|------|
| UT-VAL-01 | 规则1 试算平衡通过 | 资产=负债+权益 | `result=PASS` | ✅ |
| UT-VAL-02 | 规则1 试算不平衡 | 资产≠负债+权益 | `result=FAIL`，终止 | ✅ |
| UT-VAL-03 | 规则1 告警含年份 | 不平衡 | warnings 含 `[2024]` | ✅ |
| UT-VAL-04 | 规则1 资产为零跳过 | 全零 | `PASS` + details 含"跳过" | ✅ |
| UT-VAL-05 | 规则2 利润表勾稽通过 | 利润总额-所得税=净利润 | 无偏差告警 | ✅ |
| UT-VAL-06 | 规则2 大偏差告警 | 偏差 > 阈值 | warnings 含"利润表勾稽偏差" | ✅ |
| UT-VAL-07 | 规则2 小偏差通过 | 偏差 < 阈值 | 无告警 | ✅ |
| UT-VAL-08 | 规则2 利润总额为零跳过 | 全零 | details 含"规则2跳过" | ✅ |
| UT-VAL-09 | 规则3 现金流勾稽大偏差 | 三流净和≠净变动 | warnings 含"现金流量表勾稽偏差" | ✅ |
| UT-VAL-10 | 规则4 留存收益大偏差 | 期初+净利-分红≠期末 | warnings 含"留存收益勾稽偏差" | ✅ |
| UT-VAL-11 | 规则4 最老年份跳过 | 仅 1 年数据 | details 含"规则4跳过" | ✅ |
| UT-VAL-12 | 返回结构 | - | 含 `result`/`warnings`/`details` | ✅ |

> 对应 PRD User Story #12-15（数据校验）。硬等式（规则1）失败必须短路终止。

#### 3.1.2 `metrics/profitability.py` — 盈利 5 指标

| 用例 ID | 场景 | 预期（2024 手算） | 现状 |
|---------|------|------------------|------|
| UT-PROF-01 | 返回 5 指标 key 集合 | {毛利率,净利率,ROE,ROA,ROIC} | ✅ |
| UT-PROF-02 | 每指标含全部年份 | {2024,2023,2022} | ✅ |
| UT-PROF-03 | 毛利率 | (1000-600)/1000 = 40% | ✅ |
| UT-PROF-04 | 净利率 | 170/1000 = 17% | ✅ |
| UT-PROF-05 | ROE 优先取加权值 | indicators 有加权时取加权（44.16），非期末权益自算 | ✅ |
| UT-PROF-06 | ROE 无 indicators 时自算 | 归母净利/平均归母权益 | ✅ |
| UT-PROF-07 | ROA | 170/1000 = 17% | ✅ |
| UT-PROF-08 | ROIC | NOPAT/投入资本 ≈ 23.97% | ✅ |
| UT-PROF-09 | 营收为零 | 毛利率/净利率 = None | ✅ |

> 对应 PRD #13（盈利 5 指标）。ROE 混合来源（AKShare 加权优先 + 自算降级）是重点边界。

#### 3.1.3 `metrics/solvency.py` — 偿债 5 指标

| 用例 ID | 场景 | 预期要点 | 现状 |
|---------|------|---------|------|
| UT-SOLV-01 | 资产负债率 | 负债/资产 = 40% | ✅ |
| UT-SOLV-02 | 流动比率 | 流动资产/流动负债 | ✅ |
| UT-SOLV-03 | 速动比率 | (流动资产-存货)/流动负债 | ✅ |
| UT-SOLV-04 | 利息覆盖倍数 | EBIT/利息费用 | ✅ |
| UT-SOLV-05 | 净债务/EBITDA | (有息负债-货币资金)/EBITDA | ✅ |
| UT-SOLV-06 | 利息费用为零 | 覆盖倍数兜底处理（非除零） | 待补 |
| UT-SOLV-07 | 阈值边界 | 资产负债率 40%/65% 灯色切换 | 待补 |

> 对应 PRD #12（偿债 5 指标 + 红黄绿灯）。

#### 3.1.4 `metrics/efficiency.py` — 运营 4 指标

| 用例 ID | 场景 | 预期要点 | 现状 |
|---------|------|---------|------|
| UT-EFF-01 | 存货周转率优先取 AKShare | indicators 有值时取预计算 | ✅ |
| UT-EFF-02 | 存货周转率自算降级 | 无 indicators 时营业成本/平均存货 | ✅ |
| UT-EFF-03 | 应收账款周转率 | 营收/应收平均余额 | ✅ |
| UT-EFF-04 | 总资产周转率 | 营收/资产总计 | ✅ |
| UT-EFF-05 | 应付账款周转率 | 营业成本/应付账款 | ✅ |
| UT-EFF-06 | 白酒行业阈值覆盖 | `INDUSTRY_OVERRIDES` 覆盖存货周转率阈值 | 待补 |

> 对应 PRD #14（运营 4 指标）+ 架构 §5.2（白酒/酿酒行业 `INDUSTRY_OVERRIDES`）。

#### 3.1.5 `metrics/cashflow.py` — 现金流 6 指标

| 用例 ID | 场景 | 预期要点 | 现状 |
|---------|------|---------|------|
| UT-CF-01 | 经营现金流/净利润 | OCF/归母净利润（缺失回退合并净利润） | ✅ |
| UT-CF-02 | FCF | OCF - 资本支出 | ✅ |
| UT-CF-03 | 资本支出/折旧 | 资本支出/折旧变动 | ✅ |
| UT-CF-04 | 现金流覆盖比率 | FCF/(资本支出+利息) | ✅ |
| UT-CF-05 | FCF 收益率 | FCF/营收 | ✅ |
| UT-CF-06 | 留存现金流比率 | (FCF-分红)/FCF | ✅ |
| UT-CF-07 | FCF 为负边界 | 留存现金流比率兜底（非除零） | 待补 |
| UT-CF-08 | FCF 灯色边界 | 正且增长=绿 / 正但下降=黄 / 负=红 | 待补 |

> 对应 PRD #15（现金流 6 指标）。FCF 正负值是关键边界。

#### 3.1.6 `metrics/dupont.py` — 杜邦 3 层分解

| 用例 ID | 场景 | 预期（2024 手算） | 现状 |
|---------|------|------------------|------|
| UT-DUP-01 | L1 ROE 分解 | 净利率×总资产周转率×权益乘数 ≈ 0.2833 | ✅ |
| UT-DUP-02 | L2 净利率下钻 | 毛利率-费用率 | ✅ |
| UT-DUP-03 | L3 费用率下钻 | 销售+管理+研发+财务费用率 | ✅ |
| UT-DUP-04 | 恒等式校验 | L1 三因子乘积 = ROE | 待补 |

> 对应 PRD #18（3 层杜邦分解树）。

#### 3.1.7 `metrics/traffic_light.py` — 红黄绿灯 + 健康度评分

| 用例 ID | 场景 | 预期要点 | 现状 |
|---------|------|---------|------|
| UT-TL-01 | 双重阈值矩阵 | 绝对值灯 + 变化率灯 | ✅ |
| UT-TL-02 | max 规则 | 最终灯 = max(绝对值灯, 变化率灯) | ✅ |
| UT-TL-03 | 变化率阈值 | <20% 绿 / 20-50% 黄 / >50% 红 | ✅ |
| UT-TL-04 | 评分计算 | 绿=满分 / 黄=半分 / 红=零分 | ✅ |
| UT-TL-05 | 健康度评级 | 85-100 健康 / 60-84 关注 / <60 警告 | ✅ |
| UT-TL-06 | 四维度各 25 分 | 总分 100 | ✅ |

> 对应 PRD #16-17（双重阈值 + 健康度评分）。这是评分模型的核心，阈值边界必须覆盖。

#### 3.1.8 `metrics/relative.py` — 相对估值

| 用例 ID | 场景 | 预期要点 | 现状 |
|---------|------|---------|------|
| UT-REL-01 | PE 同业对比 | 目标 PE vs 行业均值 | ✅ |
| UT-REL-02 | PB 同业对比 | 目标 PB vs 行业均值 | ✅ |
| UT-REL-03 | 行业 PE 缺失 | 标记 N/A 不报错 | 待补 |

> 对应 PRD #19（同业对比）+ CONTEXT 估值框架。

#### 3.1.9 `metrics/garp.py` — GARP 筛选

| 用例 ID | 场景 | 预期要点 | 现状 |
|---------|------|---------|------|
| UT-GARP-01 | 四条件全满足 | PE<行业均值 ∧ 净利增长>15% ∧ ROE>15% ∧ 负债率<60% | ✅ |
| UT-GARP-02 | 部分条件不满足 | 返回不通过 + 缺失项 | ✅ |
| UT-GARP-03 | 数据缺失 | 缺失字段标记 N/A | 待补 |

> 对应 CONTEXT §GARP 定义。

#### 3.1.10 `metrics/technical.py` + `metrics/risk.py` — 技术指标与风控指标

| 用例 ID | 场景 | 预期要点 | 现状 |
|---------|------|---------|------|
| UT-TECH-01 | MACD 计算 | DIF/DEA/MACD 柱 | ✅ |
| UT-TECH-02 | RSI 计算 | 0-100 区间，超买>70/超卖<30 | ✅ |
| UT-TECH-03 | 布林带计算 | 上轨/中轨/下轨 | ✅ |
| UT-TECH-04 | KDJ 计算 | K/D/J 值 | ✅ |
| UT-RISK-01 | 最大回撤 | 峰值到谷值最大跌幅 | ✅ |
| UT-RISK-02 | 年化波动率 | 日收益标准差×√250 | ✅ |
| UT-RISK-03 | Beta | 个股 vs 沪深300 协方差/方差 | ✅ |
| UT-RISK-04 | VaR | 95% 置信区间分位数 | ✅ |
| UT-RISK-05 | K 线数据不足 | 不足 250 日时兜底 | 待补 |

> 对应 PRD #21-23（技术面）+ #28（风控指标）。沪深 300 K 线作为 Beta 基准。

### 3.2 `citation.py` — 确定性引用校验器

> 纯 Python，复用 metrics/ 纯函数重算比对。参考 FinGround 六类分类法 + ADR-0011。

| 用例 ID | 场景 | 预期 | 现状 |
|---------|------|------|------|
| UT-CIT-01 | 数值型 claim 匹配 | PASS | ✅ |
| UT-CIT-02 | 数值型 claim 不匹配 | FAIL + ground_truth + delta | ✅ |
| UT-CIT-03 | 计算型 claim 杜邦 ROE 匹配 | PASS（重算 ≈ 0.2833） | ✅ |
| UT-CIT-04 | 计算型 claim 杜邦 ROE 不匹配 | FAIL + ground_truth | ✅ |
| UT-CIT-05 | 比较型 claim 方向正确 | PASS（greater_than/less_than） | ✅ |
| UT-CIT-06 | 事件型 claim 引用存在 | PASS（key_events 命中） | ✅ |
| UT-CIT-07 | llm_inference claim 跳过 | UNVERIFIABLE | ✅ |
| UT-CIT-08 | field_ref 含 list index | 正确解析 `MA.5.4` | ✅ |
| UT-CIT-09 | CitationReport 混合汇总 | total/passed/failed/unverifiable 正确 | ✅ |
| UT-CIT-10 | CitationReport 全通过 | all_passed=True | ✅ |

> 对应 ADR-0010（幻觉率可监控）+ CONTEXT §Langfuse Score L0。`citation_pass` 上报 Langfuse trace 级。

### 3.3 `routing.py` — 条件路由

| 用例 ID | 场景 | 预期 | 现状 |
|---------|------|------|------|
| UT-RT-01 | check_cache HIT | -> validate_financials | ✅ |
| UT-RT-02 | check_cache MISS | -> fetch_data | ✅ |
| UT-RT-03 | check_cache 缺键兜底 | -> fetch_data | ✅ |
| UT-RT-04 | validate FAIL | -> __end__（短路终止） | ✅ |
| UT-RT-05 | validate PASS | -> compute_metrics | ✅ |
| UT-RT-06 | fund_manager approve | -> generate_report | ✅ |
| UT-RT-07 | fund_manager reject | -> generate_report | ✅ |
| UT-RT-08 | fund_manager return（count=0） | -> trader（退回） | ✅ |
| UT-RT-09 | fund_manager return（count=1） | -> generate_report（防死循环） | ✅ |
| UT-RT-10 | citation PASS | -> render | ✅ |
| UT-CIT-RT-11 | citation FAIL（未达上限） | -> retry | ✅ |
| UT-CIT-RT-12 | citation FAIL（达上限 3 次） | -> render（强制） | ✅ |

> 对应架构 §七条件路由 + ADR-0011（退回最多 1 次）+ ADR-0010（citation 重试最多 3 次）。

### 3.4 其他纯函数模块

| 用例 ID | 模块 | 场景 | 现状 |
|---------|------|------|------|
| UT-MOD-01 | `models.py` | AnalystReport/DebateMessage/TradeDecision 序列化 | ✅ |
| UT-NLP-01 | `nlp.py` | 股票名解析（LLM 优先 + AKShare 兜底） | ✅ |
| UT-SEARCH-01 | `app_search.py` | 模糊匹配下拉列表 | ✅ |
| UT-LLM-01 | `llm.py` | LiteLLM 调用封装（mock client） | ✅ |

---

## 四、集成测试用例

### 4.1 `graph.py` — 5 层图拓扑

| 用例 ID | 场景 | 预期 | 现状 |
|---------|------|------|------|
| IT-GRAPH-01 | 图成功编译 | graph 非 None | ✅ |
| IT-GRAPH-02 | 含 PREP 节点 | compute_metrics 等 | ✅ |
| IT-GRAPH-03 | 含 Layer I 分析师节点 | technical_analyst 等 | ✅ |
| IT-GRAPH-04 | 含 Layer II 辩论节点（两轮） | bull/bear_r1/r2 + research_manager | ✅ |
| IT-GRAPH-05 | 含 Layer III/IV 节点 | trader + risk_judge + 3 辩论者 | ✅ |
| IT-GRAPH-06 | 含 Layer V + 报告节点 | fund_manager + generate_report | ✅ |
| IT-GRAPH-07 | 含引用校验节点 | verify_citations | ✅ |

> 对应架构 §二图拓扑。验证静态节点注册与边连接，不跑真实 LLM。

### 4.2 `nodes/` — 节点编排（mock LLM + mock AKShare）

#### 4.2.1 `nodes/fetch.py`

| 用例 ID | 场景 | 预期 | 现状 |
|---------|------|------|------|
| IT-FETCH-01 | 填充全部 State 字段 | 三大报表+行情+行业+指标 | ✅ |
| IT-FETCH-02 | 写入缓存 | cache.set 调用 ≥3 次 | ✅ |
| IT-FETCH-03 | 三大报表缺失报错终止 | raise Exception | ✅ |
| IT-FETCH-04 | 同业缺失标记 N/A | peer_financials=None，不报错 | ✅ |
| IT-FETCH-05 | Step2 依赖行业归属 | 同业拉取在行业归属之后 | 待补 |

> 对应 PRD #6-11（数据准备 + 降级策略）。

#### 4.2.2 `nodes/cache.py` + `nodes/validate.py` + `nodes/compute.py`

| 用例 ID | 场景 | 预期 | 现状 |
|---------|------|------|------|
| IT-CACHE-01 | HIT 跳过 fetch | 直接进 validate | ✅ |
| IT-CACHE-02 | MISS 进 fetch | 拉取后写缓存 | ✅ |
| IT-VAL-01 | 节点编排 validate | 调 metrics/validate + 写 State | ✅ |
| IT-COMP-01 | 节点编排 compute | 调 metrics/* + 写全部衍生字段 | ✅ |

#### 4.2.3 Layer I-V Agent 节点（mock LLM）

| 用例 ID | 节点 | 场景 | 现状 |
|---------|------|------|------|
| IT-ANL-01 | analysts | 4 分析师输出 AnalystReport 结构 | ✅ |
| IT-DEB-01 | debate | bull/bear 2 轮写入 debate_history | ✅ |
| IT-RM-01 | research_manager | 综合辩论结论 | ✅ |
| IT-TRD-01 | trader | 产出 trade_decision（action∈buy/sell/hold） | ✅ |
| IT-RSK-01 | risk | 3 辩论者 + risk_judge | ✅ |
| IT-FM-01 | fund_manager | approve/reject/return | ✅ |
| IT-CITNODE-01 | citation_node | 调 verify_claims + 写 citation_pass | ✅ |
| IT-RPT-01 | report | 两步法生成 10 章报告 | ✅ |
| IT-OUT-01 | output | Word/PPT 文件生成 | ✅ |

> Agent 节点 mock LLM 返回，验证 State 读写契约与结构化输出 schema，不验证 LLM 内容质量。

### 4.3 数据层 `data/`

| 用例 ID | 模块 | 场景 | 现状 |
|---------|------|------|------|
| IT-AK-01 | `akshare_client.py` | 接口封装 + 重试 + 错误处理（mock akshare） | ✅ |
| IT-CACHE-DB-01 | `cache.py` | SQLite 读写 + TTL 过期 | ✅ |

> PRD 标注 data/akshare_client.py 走集成测试人工验证；cache.py 薄封装。真实 AKShare 调用放 E2E。

### 4.4 导出层 `export/`

| 用例 ID | 模块 | 场景 | 现状 |
|---------|------|------|------|
| IT-PARSE-01 | `parser.py` | Markdown 解析为结构化段 | ✅ |
| IT-DOCX-01 | `docx_exporter.py` | 生成 .docx 文件可打开 | ✅ |
| IT-PPTX-01 | `pptx_exporter.py` | 生成 .pptx 文件可打开 | ✅ |

> 对应 PRD #31-32（Word/PPT 导出）。

### 4.5 三模式 ReAct Agent（集成）

| 用例 ID | 场景 | 预期 | 现状 |
|---------|------|------|------|
| IT-AGENT-01 | 深度模式工具集 | 含 search_stock + run_deep_analysis + web_search | ✅ |
| IT-AGENT-02 | 快速模式工具集 | 仅 web_search，不暴露 run_deep_analysis | ✅ |
| IT-AGENT-03 | 追问模式工具集 | 仅 web_search，不暴露 run_deep_analysis | ✅ |
| IT-AGENT-04 | max_iterations | 深度=10 / 快速=3 / 追问=3 | ✅ |
| IT-REACT-01 | ReAct 循环 | 思考->工具调用->观察->回答 | ✅ |
| IT-FOLLOWUP-01 | 追问上下文注入 | 报告+summary+chat_history | ✅ |
| IT-DEEP-TOOL-01 | run_deep_analysis 流式工具 | yield PROGRESS 事件 | ✅ |

> 对应 CONTEXT §三模式设计 + ADR-0014（统一编排）+ ADR-0013（快速模式）。

---

## 五、E2E 测试用例（真实链路，禁 mock）

> 通过 Playwright 驱动前端，FastAPI + Vite + 真实 LLM 全栈。无 API Key 时 skipif 跳过。

### 5.1 深度模式完整管线

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| E2E-PIPE-01 | 5 层全流程（600519） | final_report 含股票名；analyst_reports 含 technical；debate_history=4 条；final_trade_decision.action∈buy/sell/hold；fund_manager_decision∈approve/reject/revise | ✅ |
| E2E-PIPE-02 | PREP -> Layer I-V -> 报告 | 各层产出齐全 | ✅ |

> 对应架构 §4.3 HIT/MISS 两条路径 + PRD #2（自动 5 层分析）。

### 5.2 对话流与澄清

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| E2E-CLARIFY-01 | 歧义输入"光模块龙头" | Agent 反问澄清，非直接出管线 | ✅ |
| E2E-CLARIFY-02 | 明确股票名"贵州茅台" | search_stock 对话流展示 | ✅ |
| E2E-CLARIFY-03 | 无 DSML 文本泄漏 | 页面无 `｜｜DSML｜｜` 等标记 | ✅ |
| E2E-CLARIFY-04 | 管线 UI 不过早出现 | 澄清阶段无"深度分析进行中" | ✅ |

> 对应 CONTEXT §Natural Language Input + ADR-0017（意图澄清对话流）。

### 5.3 三模式回归

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| E2E-MODE-01 | 模式下拉框回归 | 可打开 + 浮在最上层 | ✅ |
| E2E-MODE-02 | 快速模式 chat | web_search 横幅 + 秒级响应 | ✅ |
| E2E-MODE-03 | 追问模式 | 基于已有报告问答 | ✅ |

### 5.4 会话与流式

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| E2E-SESS-01 | 会话侧边栏 | 新建/切换/搜索/重命名/删除 | ✅ |
| E2E-SESS-02 | 流式逐 Token | SSE 渐进渲染 | ✅ |
| E2E-SESS-03 | 报告卡片位置 | 用户问题在报告之前（不置顶） | ✅ |
| E2E-SESS-04 | 会话状态流转 | clarifying/running/completed/failed | 待补 |

> 对应 ADR-0012（会话与流式）+ CONTEXT §Session。

### 5.5 搜索与下拉

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| E2E-SEARCH-01 | 股票搜索下拉 | 模糊匹配候选列表 | ✅ |
| E2E-SEARCH-02 | React 搜索浏览器 | 前端渲染候选 | ✅ |

> 对应 PRD #1（搜索框 + 下拉选择）。

### 5.6 可观测性

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| E2E-LF-01 | Langfuse 追踪（深度） | Trace -> span(run_deep_analysis) -> 各 Agent span | ✅ |
| E2E-LF-02 | Langfuse 追踪（追问） | 每次追问独立 Trace | ✅ |
| E2E-LF-03 | citation_pass 上报 | trace 级 boolean score | ✅ |

> 对应 ADR-0015/0016 + CONTEXT §Trace/Span/Generation/Score。

### 5.7 图表渲染

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| E2E-CHART-01 | 前端 ECharts 渲染 | 图表数据来自 PREP | ✅ |
| E2E-CHART-02 | docx/pptx matplotlib 图 | 导出文件含 PNG 图 | 待补 |

> 对应 CONTEXT §Report（一次收集两处渲染）。

---

## 六、前端行为验证用例（Playwright 驱动）

> 本节专门覆盖前端 UI 组件的渲染、交互与状态流转，全部经 Playwright 驱动真实浏览器（Chromium headless）。
> 前端源码：`frontend/src/App.tsx`（8 个组件）+ `frontend/src/types.ts`（SSE 事件契约）。
> 约束：**禁止 mock，禁止用 `requests`/`httpx` 直调后端**；真实 LLM 用例需配置 API Key，无 Key 时 `skipif` 跳过。

### 6.1 应用状态与初始化（`appState`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-STATE-01 | 初始空状态 | `appState=empty`，渲染 EmptyState，输入框聚焦 | ✅ |
| FE-STATE-02 | 分析中状态 | `appState=analyzing`，渲染 PipelineCard，输入框禁用 | ✅ |
| FE-STATE-03 | 报告就绪状态 | `appState=report`，渲染 ReportCard + 图表 | ✅ |
| FE-STATE-04 | 澄清中状态 | `appState=clarifying`，渲染对话气泡，无 PipelineCard | ✅ |
| FE-STATE-05 | API Key 持久化 | localStorage 保存 `apiKey`，刷新后自动恢复 | ✅ |
| FE-STATE-06 | userId 持久化 | localStorage 保存 `userId`，刷新后复用 | 待补 |

> 对应架构 §前端状态机 + CONTEXT §Session。澄清阶段不得提前出现"深度分析进行中"。

### 6.2 EmptyState 空状态页（`App.tsx:894`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-EMPTY-01 | 空状态布局 | 标题 + 副标题 + 输入框 + 模式选择可见 | ✅ |
| FE-EMPTY-02 | API Key 未配置提示 | 显示"去配置"按钮 | ✅ |
| FE-EMPTY-03 | 输入并发送 | 输入文本后按 Enter/点发送触发 onSend | ✅ |
| FE-EMPTY-04 | 模式切换占位符 | 切换深度/快速时 textarea placeholder 变化 | ✅ |

> 对应 PRD #1（搜索框）+ ADR-0013（模式选择）。

### 6.3 Sidebar 会话侧边栏（`App.tsx:753`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-SIDEBAR-01 | 新建会话 | 点击"新建会话"按钮，列表新增条目 | ✅ |
| FE-SIDEBAR-02 | 切换会话 | 点击列表项，currentSessionId 变更，主区加载历史 | ✅ |
| FE-SIDEBAR-03 | 搜索会话 | 输入关键词过滤会话列表 | ✅ |
| FE-SIDEBAR-04 | 重命名会话 | 双击/按钮进入编辑态，提交后 display_name 更新 | ✅ |
| FE-SIDEBAR-05 | 删除会话 | 删除按钮移除条目，删除当前会话后回到空状态 | ✅ |
| FE-SIDEBAR-06 | 折叠/展开侧边栏 | onToggle 切换 isOpen，布局 leftInset 变化 | ✅ |
| FE-SIDEBAR-07 | 会话列表排序 | 按 created_at 倒序展示 | 待补 |
| FE-SIDEBAR-08 | 会话时间显示 | created_at 正确格式化（非 "Invalid Date"） | ✅ 修复 |

> 对应 ADR-0012（会话管理）+ CONTEXT §Session。
> ✅ **BUG #007 已修复**（incident 007）：历史脏数据 `created_at='chat'`/'analysis' 已迁移修复 + 后端 `_normalize_created_at` 兜底 + 前端 `formatSessionTime` 兜底。回归测试 `tests/test_session_store_time.py` + `tests/e2e/test_sidebar_invalid_date.py`。

### 6.4 模式选择器（EmptyState 下拉框 `App.tsx:947` + ChatInputBar 双按钮 `App.tsx:1705`）

> 前端有两套模式选择器：EmptyState（空状态）使用下拉框（标签"模式："），ChatInputBar（会话激活后）使用双按钮切换。默认 deep。

**EmptyState 下拉框（`test_dropdown.py` / `test_mode_regression.py` 验证）：**

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-INPUT-01 | 下拉框打开 | 点击"模式："按钮，浮层显示"快速模式"+"深度研究"两项 + 描述 | ✅ |
| FE-INPUT-02 | 下拉框浮层层级 | 浮在最上层（z-70），不被遮挡 | ✅ |
| FE-INPUT-03 | 切换快速模式 | 选中"快速模式"后 placeholder 变为"输入问题，如：..." | ✅ |
| FE-INPUT-04 | 切换回深度研究 | 再次打开选"深度研究"，placeholder 恢复"输入股票名称或代码" | ✅ |
| FE-INPUT-05 | 点击外部关闭 | 点击空白区域 overlay（z-60）关闭下拉 | ✅ |
| FE-INPUT-06 | Enter 发送 | 输入框非空时 Enter 触发 onSend | ✅ |
| FE-INPUT-07 | 分析中禁用 | analyzing 状态下输入框禁用/发送按钮置灰 | 待补 |
| FE-INPUT-08 | 默认模式 | 首次加载默认 **deep**（深度研究），非 quick | ✅ |

**ChatInputBar 双按钮切换（会话激活后）：**

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-INPUT-09 | 双按钮可见 | "深度研究" / "快速对话" 两个切换按钮 | ✅ |
| FE-INPUT-10 | 按钮切换 | 点击按钮直接切换模式（无下拉浮层） | ✅ |

> 对应 ADR-0013（模式）。`test_dropdown.py` + `test_mode_regression.py` 全覆盖 EmptyState 下拉框。
> ⚠️ **E2E 实测发现**：默认模式已从 quick 改为 deep（`App.tsx:51`）；EmptyState 下拉框选项文案为"快速模式"（非"快速对话"），ChatInputBar 双按钮文案为"快速对话"。

### 6.5 ApiKeyModal 配置弹窗（`App.tsx:1762`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-APIKEY-01 | 打开弹窗 | 点击"去配置"显示模态框 | ✅ |
| FE-APIKEY-02 | 密码输入框 | input type=password 隐藏明文 | ✅ |
| FE-APIKEY-03 | 确认保存 | 填入 Key 后点"确认"，localStorage 写入 + 关闭弹窗 | ✅ |
| FE-APIKEY-04 | 关闭弹窗 | onClose 关闭，不保存 | 待补 |
| FE-APIKEY-05 | 空 Key 校验 | 空值提交时阻止/提示 | 待补 |

> 对应 e2e_quick_chat.py 的 API Key 配置流程。

### 6.6 ThinkingBanner 思考过程折叠面板（`App.tsx:1154`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-THINK-01 | 思考流式渲染 | thinking_token 逐字渐进显示 | ✅ |
| FE-THINK-02 | Kimi 风格折叠 | 默认折叠，点击展开查看完整思考 | ✅ |
| FE-THINK-03 | 流式中状态标识 | streaming=true 时显示"思考中..."动效 | 待补 |
| FE-THINK-04 | 无 DSML 泄漏 | 面板内容不含 `｜｜DSML｜｜` 等内部标记 | ✅ |

> 对应 ADR-0017（思考过程展示）+ CONTEXT §Thinking。

### 6.7 SearchBanner 搜索结果折叠面板（`App.tsx:1233`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-SEARCH-BANNER-01 | 搜索中状态 | searchStatus=searching 显示加载态 | ✅ |
| FE-SEARCH-BANNER-02 | 结果渲染 | searchResults 逐条展示标题+URL+摘要 | ✅ |
| FE-SEARCH-BANNER-03 | Kimi 风格折叠 | 默认折叠，点击展开 | ✅ |
| FE-SEARCH-BANNER-04 | 快速模式横幅 | 快速模式显示 web_search 横幅 | ✅ |
| FE-SEARCH-BANNER-05 | 搜索错误状态 | searchStatus=error 显示错误提示 | 待补 |

> 对应 ADR-0013（快速模式 web_search）。

### 6.8 PipelineCard 管线进度卡（`App.tsx:1303`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-PIPE-01 | 6 阶段进度 | 渲染 6 个阶段步骤（PREP/Layer I-V/报告） | ✅ |
| FE-PIPE-02 | 节点开始高亮 | node_start 时当前节点高亮 | ✅ |
| FE-PIPE-03 | 节点完成打勾 | node_complete 时 completedNodes 标记完成 | ✅ |
| FE-PIPE-04 | 进度条百分比 | progress 数值更新进度条 | ✅ |
| FE-PIPE-05 | 分析师卡片 | 渲染 4 分析师产出卡片 | ✅ |
| FE-PIPE-06 | 实时日志滚动 | nodeOutputs 日志区自动滚动 | 待补 |
| FE-PIPE-07 | 澄清阶段不出现 | appState=clarifying 时不渲染 PipelineCard | ✅ |

> 对应架构 §4.3 管线可视化 + 现有 `e2e_deep_mode_conversation_flow.py` 时序验证。

### 6.9 ReportCard 报告卡片（`App.tsx:1513`）

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-REPORT-01 | 流式渲染 | report_chunk 逐段渐进显示 | ✅ |
| FE-REPORT-02 | 流式标识 | streaming=true 时显示加载态 | ✅ |
| FE-REPORT-03 | 报告头部 | 显示股票名 + 耗时 durationMs | ✅ |
| FE-REPORT-04 | Markdown 表格渲染 | 前端解析 markdown 表格正常显示 | ✅ |
| FE-REPORT-05 | 图表区渲染 | chartData 渲染 ECharts | ✅ |
| FE-REPORT-06 | 网络来源展示 | webSources 逐条展示 | ✅ |
| FE-REPORT-07 | 免责声明 | 底部显示免责声明 | ✅ |
| FE-REPORT-08 | 导出按钮 | 显示 Word/PPT 导出入口 | 待补 |
| FE-REPORT-09 | 位置不置顶 | 报告卡片在用户问题之后，不被顶到顶部 | ✅ |

> 对应 PRD #30-34（报告生成+导出）+ ADR-0012（报告卡片位置）。现有 `test_report_order.py` 覆盖位置约束。

### 6.10 SSE 事件契约处理（`types.ts` + App 事件分发）

> 验证前端对后端 19 种 SSE 事件的正确分发与渲染。这是前后端契约的关键。

| 用例 ID | 事件类型 | 验证点 | 现状 |
|---------|---------|--------|------|
| FE-SSE-01 | `analysis_start` | 触发 appState=analyzing | ✅ |
| FE-SSE-02 | `node_start`/`node_complete` | 更新 PipelineCard 节点状态 | ✅ |
| FE-SSE-03 | `parsing` | 显示"解析中"提示 | ✅ |
| FE-SSE-04 | `resolved`/`stock_resolved` | 显示已解析股票名 | ✅ |
| FE-SSE-05 | `thinking_token` | 写入 ThinkingBanner | ✅ |
| FE-SSE-06 | `tool_call`/`tool_result` | 更新 ReAct 工具调用展示 | ✅ |
| FE-SSE-07 | `report_chunk` | 拼接 ReportCard 流式内容 | ✅ |
| FE-SSE-08 | `chat_token` | 拼接对话气泡内容 | ✅ |
| FE-SSE-09 | `chat_done` | 标记对话完成，恢复输入框 | ✅ |
| FE-SSE-10 | `search_start`/`search_result` | 更新 SearchBanner | ✅ |
| FE-SSE-11 | `report_ready` | 切换 appState=report + 渲染图表 | ✅ |
| FE-SSE-12 | `session_created` | 新建会话条目 | ✅ |
| FE-SSE-13 | `awaiting_input` | 切换 appState=clarifying | ✅ |
| FE-SSE-14 | `error` | 显示错误气泡，恢复输入框 | ✅ |
| FE-SSE-15 | `done` | 标记分析完成 | ✅ |
| FE-SSE-16 | `search_error` | 更新 searchStatus=error | 待补 |

> 对应架构 §SSE 事件流 + types.ts 全部事件类型。

### 6.11 滚动与布局行为

| 用例 ID | 场景 | 验证点 | 现状 |
|---------|------|--------|------|
| FE-SCROLL-01 | 自动滚动到底 | 新消息到达时 autoScroll 滚动到底部 | ✅ |
| FE-SCROLL-02 | scrollIntoView 跟随 | 新气泡 scrollIntoView 进视图 | 待补 |
| FE-SCROLL-03 | 侧边栏折叠布局 | leftInset 随侧边栏宽度调整 | ✅ |
| FE-SCROLL-04 | 长报告滚动 | 报告超长时可独立滚动 | 待补 |

> 对应 ADR-0012（流式渲染滚动）。

---

## 七、追溯矩阵（PRD User Story -> 测试用例）

| PRD # | User Story | 主要测试用例 | 覆盖状态 |
|-------|-----------|-------------|---------|
| 1 | 搜索框 + 下拉选股 | FE-EMPTY-01~04, FE-INPUT-01~06, E2E-SEARCH-01/02, UT-SEARCH-01 | ✅ |
| 2 | 输入代码自动 5 层分析 | FE-PIPE-01~05, E2E-PIPE-01/02, IT-GRAPH-01 | ✅ |
| 3 | 可选对标股票 | IT-FETCH-04, UT-REL-01 | ✅ |
| 4 | 无对标自动选 Top 5 | UT-REL-01（待补自动选取） | ⚠️ 部分 |
| 5 | 股票不存在报错 | IT-FETCH-03, FE-SSE-14 | ✅ |
| 6 | 拉取近 5 年三大报表 | IT-FETCH-01, IT-AK-01 | ✅ |
| 7 | 拉取行情+行业 | IT-FETCH-01 | ✅ |
| 8 | 拉取同业数据 | IT-FETCH-04 | ✅ |
| 9 | 缓存 HIT 秒级返回 | IT-CACHE-01/02 | ✅ |
| 10 | 非必需数据缺失标注 N/A | IT-FETCH-04, UT-REL-03 | ✅ |
| 11 | 必需数据缺失报错 | IT-FETCH-03 | ✅ |
| 12-15 | 勾稽校验 4 规则 | UT-VAL-01~12 | ✅ |
| 12(重) | 偿债 5 指标 + 灯 | UT-SOLV-01~07 | ✅(边界待补) |
| 13(重) | 盈利 5 指标 + 灯 | UT-PROF-01~09 | ✅ |
| 14(重) | 运营 4 指标 + 灯 | UT-EFF-01~06 | ✅(行业覆盖待补) |
| 15(重) | 现金流 6 指标 + 灯 | UT-CF-01~08 | ✅(边界待补) |
| 16 | 双重阈值评判 | UT-TL-01~03 | ✅ |
| 17 | 健康度评分 + 评级 | UT-TL-04~06 | ✅ |
| 18 | 杜邦 3 层分解 | UT-DUP-01~04 | ✅(恒等式待补) |
| 19 | 同业对比表 | UT-REL-01/02 | ✅ |
| 20 | 红灯指标汇总 | IT-ANL-01（基本面） | ✅ |
| 21-23 | 技术面指标 + 支撑压力 + 趋势 | UT-TECH-01~04, IT-ANL-01 | ✅ |
| 24-25 | 舆情新闻 + 情感 | IT-ANL-01（舆情） | ✅ |
| 26 | Bull/Bear 辩论摘要 | IT-DEB-01, IT-RM-01, E2E-PIPE-01 | ✅ |
| 27 | Trader 交易建议 | IT-TRD-01, E2E-PIPE-01 | ✅ |
| 28 | Risk 压力测试 + 风控指标 | IT-RSK-01, UT-RISK-01~04 | ✅ |
| 29 | Fund Manager 审批 | IT-FM-01, E2E-PIPE-01 | ✅ |
| 30 | 执行摘要（两步法） | IT-RPT-01, FE-REPORT-01~03 | ✅ |
| 31 | 导出 Word | IT-DOCX-01, FE-REPORT-08, E2E-CHART-02 | ✅ |
| 32 | 导出 PPT | IT-PPTX-01, FE-REPORT-08 | ✅ |
| 33 | 免责声明 | IT-RPT-01, FE-REPORT-07 | ✅ |
| 34 | Markdown 表格前端渲染 | FE-REPORT-04, E2E-CHART-01 | ✅ |
| (前端) | 应用状态机 empty/analyzing/report/clarifying | FE-STATE-01~06 | ✅(userId 待补) |
| (前端) | 会话侧边栏管理 | FE-SIDEBAR-01~07 | ✅(排序待补) |
| (前端) | 思考过程 Kimi 风格折叠 | FE-THINK-01~04 | ✅(动效待补) |
| (前端) | 搜索结果 Kimi 风格折叠 | FE-SEARCH-BANNER-01~05 | ✅(错误态待补) |
| (前端) | 管线进度可视化 | FE-PIPE-01~07 | ✅(日志滚动待补) |
| (前端) | 报告卡片位置不置顶 | FE-REPORT-09, E2E-SESS-03 | ✅ |
| (前端) | SSE 事件契约（19 种） | FE-SSE-01~16 | ✅(search_error 待补) |
| (前端) | 流式渲染自动滚动 | FE-SCROLL-01~04 | ✅(部分待补) |
| (前端) | API Key 配置弹窗 | FE-APIKEY-01~05 | ✅(校验待补) |
| (前端) | 三模式切换 UI | FE-INPUT-01~08, E2E-MODE-01~03 | ✅(禁用态待补) |

> ⚠️ 标记项为边界场景待补全，不阻断主链路。

---

## 八、测试执行约定

### 8.1 命令

```bash
# 单元测试（CI 门禁，秒级）
uv run pytest tests/metrics tests/test_citation.py tests/test_routing.py tests/test_models.py -q

# 集成测试（含 mock）
uv run pytest tests/nodes tests/test_graph_5layer.py tests/export tests/data -q

# E2E 测试（需 Docker 全栈 + API Key）
docker compose up -d
uv run pytest tests/e2e/test_*.py -s
# 或单独脚本
python tests/e2e/e2e_deep_mode_conversation_flow.py

# 覆盖率
uv run pytest --cov=finance_agent --cov-report=term-missing

# Lint / 类型检查（提交前）
uv run ruff check .
uv run mypy src
```

### 8.2 E2E 前置检查

E2E 脚本内置服务探测（参考 `e2e_deep_mode_conversation_flow.py`）：
- 后端 `127.0.0.1:8000` 在监听 + `/api/health` 可达
- 前端 `127.0.0.1:5173` 在监听
- `LLM_API_KEY` / `DEEPSEEK_API_KEY` 已配置

任一不满足直接 `[FAIL]` 退出，不进入 Playwright。

### 8.3 pytest 配置（`pyproject.toml`）

- `testpaths = ["tests"]`、`pythonpath = ["src"]`、`asyncio_mode = "auto"`
- E2E 真实 LLM 测试用 `pytestmark = pytest.mark.skipif(not env_key, ...)` 守卫

---

## 九、缺陷追踪与质量指标

### 9.1 缺陷记录

系统性问题记录在 `docs/incidents/`，编号文档 + 更新 `docs/incidents/README.md` 索引。已知历史问题：

| 编号 | 主题 | 关联测试 |
|------|------|---------|
| 001 | LLM 幻觉 | UT-CIT-*（引用校验） |
| 002 | 报告准确性 | tests/validation/300308 |
| 003 | 股票名与 N/A 处理 | UT-NLP-01, IT-FETCH-04 |
| 004 | 数据准确性 | tests/validation/600519 |
| 005 | GARP/Dupont 测试污染 | UT-GARP-*, UT-DUP-* |
| 006 | Citation 无限循环 | UT-CIT-RT-11/12（重试上限） |
| 007 | 侧边栏 "Invalid Date" | FE-SIDEBAR-08（已修复） |
| 008 | E2E 脚本选择器漂移 | test_dropdown/mode_regression/quick_chat 等（已修复） |

### 9.2 质量指标（Langfuse Score 三层）

| 层级 | 指标 | 方式 | 挂载点 |
|------|------|------|--------|
| L0 | `citation_pass: bool` | 确定性（verify_claims） | trace 级 |
| L1 | 杜邦分层/勾稽 | Code Evaluator（复用 metrics/） | - |
| L1 | 分析深度/逻辑/表达 | LLM-as-Judge | - |
| L2 | 标的快照 | Dataset + Experiment | CI 回归 |

> 禁止让 LLM-as-Judge 判数字对错（评审 LLM 自身会幻觉，ADR-0010）。

---

## 十、待补全清单（按优先级）

| 优先级 | 用例 ID | 说明 |
|--------|---------|------|
| 高 | UT-SOLV-06/07 | 偿债指标零值兜底 + 阈值边界 |
| 高 | UT-CF-07/08 | FCF 负值兜底 + 灯色边界 |
| 高 | FE-APIKEY-04/05 | API Key 弹窗关闭 + 空值校验 |
| 高 | FE-INPUT-07 | 分析中输入框禁用态 |
| 中 | UT-EFF-06 | 白酒行业 `INDUSTRY_OVERRIDES` 阈值覆盖 |
| 中 | UT-DUP-04 | 杜邦恒等式校验 |
| 中 | UT-RISK-05 | K 线数据不足兜底 |
| 中 | E2E-SESS-04 | 会话状态流转全路径 |
| 中 | FE-SSE-16 | search_error 事件前端处理 |
| 中 | FE-REPORT-08 | 报告卡片导出按钮入口 |
| 中 | FE-PIPE-06 | 管线实时日志自动滚动 |
| 中 | FE-SCROLL-02/04 | scrollIntoView 跟随 + 长报告滚动 |
| 低 | UT-REL-03 | 行业 PE 缺失 N/A |
| 低 | E2E-CHART-02 | docx/pptx matplotlib 图导出 |
| 低 | FE-STATE-06 | userId 持久化复用 |
| 低 | FE-SIDEBAR-07 | 会话列表排序 |
| 低 | FE-THINK-03 | 思考流式中状态动效 |
| 低 | FE-SEARCH-BANNER-05 | 搜索错误状态展示 |

---

## 附录 A：测试目录结构

```
tests/
├── conftest.py              # 共享 fixtures（合成财报数据）
├── fixtures/                # 真实标的数据快照（600519_metrics_raw.json）
├── metrics/                 # metrics/ 单元测试（9 模块）
├── nodes/                   # 节点集成测试（mock LLM + mock AKShare）
├── data/                    # 数据层集成测试
├── export/                  # 导出层测试
├── e2e/                     # E2E 测试（真实链路，Playwright）
├── scripts/                 # 手动验证脚本
└── validation/              # 人工验证报告
```

## 附录 B：设计文档引用

| 文档 | 用途 |
|------|------|
| [PRD.md](PRD.md) | User Stories + Testing Decisions |
| [architecture.md](architecture.md) | 图拓扑 + 节点规格 + 条件路由 |
| [../CONTEXT.md](../CONTEXT.md) | 术语表 + 三模式 + Langfuse 语义 |
| [adr/0011](adr/0011-five-layer-architecture.md) | 5 层架构 |
| [adr/0014](adr/0014-agent-harness-orchestration.md) | ReAct 统一编排 |
| [adr/0015](adr/0015-langfuse-tracing-integration.md) | Langfuse 追踪 |
| [adr/0016](adr/0016-langfuse-prompt-management.md) | Prompt 管理 |
| [adr/0017](adr/0017-intent-clarification-conversation-flow.md) | 意图澄清对话流 |
