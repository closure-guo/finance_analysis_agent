# Slice 5 设计文档：接入非财务事件数据（Issue #8）

## 背景
为舆情分析师（ADR-0011 Layer I）注入关键非财务事件（提价、渠道变革、业绩超预期等），提升分析深度。采用三级回退架构，确保 demo 稳定性。

## 架构

```
L1: data/key_events.json（预构建库）── DEMO 默认
L2: WebSearch（权威域名限制）── EVENT_SOURCE=auto 时启用
L3: "事件数据暂时不可用" ── 兜底
```

## 领域术语

**Key Event（关键事件）**：已发生且对经营有持续影响的非财务事实。作为舆情分析师（ADR-0011 Layer I）的输入之一。影响未来 3-5 年价值判断，但非财务报表数字。

## 数据层

### data/hot_stocks.json
约80只股票：市值前50 + 行业龙头（白酒、银行、新能源、科技、医药等）。

结构：
```json
{
  "version": "2024-06",
  "stocks": [
    {"code": "600519", "name": "贵州茅台", "sector": "白酒"},
    ...
  ]
}
```

### data/key_events.json
- **600519**：完整填充 5 条
- **Top-10 行业龙头**：各填充 1-2 条标志性事件
- **其余股票**：空列表（结构性空）

事件结构：
```json
{
  "600519": [
    {
      "date": "2023-11-01",
      "type": "提价",
      "title": "茅台上调出厂价20%",
      "summary": "53度飞天茅台出厂价由969元上调至1169元，为近6年首次提价",
      "impact": "positive",
      "source": "公司公告",
      "url": null,
      "ongoing": false
    }
  ]
}
```

事件类型枚举：`提价`、`渠道变革`、`业绩超预期`、`业绩低于预期`、`管理层变动`、`政策影响`、`产品发布`、`并购/重组`、`监管处罚`

impact 枚举：`positive`、`negative`、`neutral`

## 事件模块

### src/finance_agent/events/config.py
- `ALLOWED_DOMAINS`：caixin.com, stcn.com, cs.com.cn, eastmoney.com, hexun.com
- `EVENT_SOURCE`：从环境变量读取，默认 "builtin"
- `DEMO_MODE`：EVENT_SOURCE == "builtin"

### src/finance_agent/events/preset_loader.py
- `load_preset_events(stock_code: str) -> list[dict] | None`
- 从 data/key_events.json 加载
- code 不在库中 → 返回 None（触发 L2/L3）
- code 在库中但事件为空列表 → 返回 []（结构性空）

### src/finance_agent/events/web_fetcher.py
- `fetch_events_from_web(stock_code: str, stock_name: str) -> list[dict] | None`
- 构造搜索查询：`"{stock_name} {stock_code} 2024 2025 提价 渠道 业绩"`
- WebSearch 限制域名和时间（past year）
- LLM 提取结构化事件（title/summary/date/type/impact/source）
- 失败返回 None

### src/finance_agent/events/fallback.py
- `fallback_annotation() -> list[dict]`
- 返回单条事件：`{"type": "数据状态", "title": "事件数据暂时不可用", "summary": "当前未接入实时事件源，仅展示预构建库数据", "impact": "neutral", "source": "system"}`

### src/finance_agent/events/pipeline.py
- `fetch_key_events(stock_code: str, stock_name: str) -> list[dict]`
- L1 → L2 → L3 回退链
- 时间过滤：只保留最近 2 年事件，`ongoing=true` 除外
- 返回事件列表（至少不会空，L3 兜底）

## 集成点

### state.py
新增字段：`key_events: list[dict] | None`

### fetch.py
在季度数据之后、同业数据之前，调用 `fetch_key_events`：
```python
try:
    from finance_agent.events.pipeline import fetch_key_events
    events = fetch_key_events(code, info.get("name", ""))
    result["key_events"] = events
except Exception:
    result["key_events"] = []
```

### formatters.py
新增 `format_key_events(events: list[dict] | None) -> str`：
- Markdown 列表展示事件（日期 | 类型 | 标题 | 影响）
- 结构性空 → "暂无重大非财务事件记录"
- 兜底事件 → 灰色提示样式

### ia.py
`_build_context` 中注入：
```python
from finance_agent.formatters import format_key_events
sections.append(format_key_events(state.get("key_events")))
```

### 舆情分析师（sentiment analyst）
事件作为独立数据块注入 PREP，供舆情分析师（ADR-0011 Layer I）使用：

**正面事件**（impact=positive）：在第4章（估值分析）中作为价值驱动因素引用，说明事件如何支撑当前估值或未来增长预期。

**负面/中性事件**（impact=negative/neutral）：在第5章（风险提示）中作为风险因素引用，分析事件对经营的潜在威胁或不确定性。

**Prompt 约束**：事件分析禁止复述财务指标已量化的结论。如果事件的影响已完全体现在报表数字中，简要引用即可，重心放在财务数字无法表达的部分（战略连贯性、渠道冲突、政策不确定性）。

## 降级策略

| 场景 | 行为 |
|------|------|
| DEMO_MODE (默认) | 只读 L1 预构建库 |
| L1 命中（有事件） | 直接返回预构建事件（过滤时间后） |
| L1 命中（空列表） | 返回 []，提示"暂无重大非财务事件记录" |
| L1 未命中 + auto | 尝试 L2 WebSearch |
| L2 失败 | 返回 L3 兜底提示 |
| 网络不可用 | 自动降级到 L3，不抛异常 |

## 文件清单

新建：
- data/hot_stocks.json
- data/key_events.json
- src/finance_agent/events/__init__.py
- src/finance_agent/events/config.py
- src/finance_agent/events/preset_loader.py
- src/finance_agent/events/web_fetcher.py
- src/finance_agent/events/fallback.py
- src/finance_agent/events/pipeline.py
- docs/design/slice5_events.md

修改：
- src/finance_agent/state.py
- src/finance_agent/nodes/fetch.py
- src/finance_agent/nodes/analysts.py  # 舆情分析师（待实现，同 technical_analyst 模式）
- src/finance_agent/formatters.py
- src/finance_agent/prompts/sentiment_analyst.md  # 待创建

## 测试策略

1. 600519 应返回完整事件列表（L1 命中，时间过滤后保留）
2. 000858（在库但空列表）应返回 []，显示"暂无重大非财务事件记录"
3. 000888（不在库）应返回 L3 兜底事件
4. EVENT_SOURCE=auto 时应尝试 WebSearch（需网络）
5. 事件应正确渲染在 IA report 中，positive 在第4章，negative 在第5章
