# 003: 股票名称获取失败 + 评分模型 NaN 处理缺陷

**日期**: 2026-06-03
**状态**: 已修复
**关联 Issue**: #5 (Bug: 指标计算与评分模型准确性)

---

## 问题 1: 股票名称/行业信息获取失败

### 症状

- `fetch_industry("600519")` 返回 `{}`
- `fetch_stock_quote("600519")` 返回 `{}`
- 报告封面股票名称显示 "N/A"

### 根因

环境中 **东方财富 push2.eastmoney.com 被完全屏蔽**：
- DNS 解析 ✅ 成功
- TCP 连接 ✅ 成功
- SSL 握手 ✅ 成功
- HTTP GET ❌ 服务端立即关闭连接（`RemoteDisconnected`）

`fetch_industry` 和 `fetch_stock_quote` 的主源均依赖东方财富 API，失败且无降级方案。

### 修复方案

| 组件 | 修复 | 文件 |
|------|------|------|
| 名称降级 | `_fetch_name_fallback()` 使用 `stock_info_a_code_name` | `akshare_client.py:112-121` |
| 行业降级 | `_fetch_industry_cninfo()` 使用 `stock_industry_change_cninfo`（巨潮资讯） | `akshare_client.py:123-130` |

巨潮资讯 API 返回 `行业中类` = "白酒"，与行业阈值覆盖匹配成功。

---

## 问题 2: 评分模型一刀切 — 白酒行业存货周转率被误判为红灯

### 症状

茅台(600519) 存货周转率 0.3 次被标为 🔴（库存积压风险）。

### 根因

通用阈值要求存货周转率 >= 5 为 🟢、>= 2 为 🟡。白酒行业基酒需陈酿 3-5 年，周转率天然偏低，0.3 次属正常经营模式。

### 修复方案

1. `traffic_light.py` 添加 `INDUSTRY_OVERRIDES`：
   - `"白酒"`: 存货周转率阈值 `(0.5, 0.2, True)`
   - `"酿酒"`: 存货周转率阈值 `(0.5, 0.2, True)`

2. `assess_traffic_lights()` 接受可选 `industry` 参数，优先匹配行业覆盖阈值。

3. `compute.py` 传入 `industry=state["industry_info"].get("industry")`。

### 效果

- 通用阈值：存货周转率 = 🔴
- 行业适配（白酒）：存货周转率 = 🟡（正确识别为基酒陈酿特征）
- 2025 健康度：70.0 → 78.1

---

## 问题 3: 净债务/EBITDA 对净现金公司计算为 NaN 导致全部红灯

### 症状

茅台无短期借款/长期借款/应付债券，"净债务/EBITDA" 全部显示 `nan`，红绿灯系统判为 🔴。

### 根因

代码使用 `val or 0` 处理缺失值：

```python
short_debt = balance_sheet.iloc[i].get("短期借款", 0) or 0
```

当字段存在但值为 `NaN` 时，`float('nan') or 0` 返回 `NaN`（**Python 中 NaN 的布尔值为 True**）。

```
>>> import math
>>> bool(math.nan)
True
>>> math.nan or 0
nan
```

有息负债计算：`NaN + 0 + 0 + 4420万` = `NaN`
净债务：`NaN - 516亿现金` = `NaN`
净债务/EBITDA：`NaN / 1200亿` = `NaN`

### 修复方案

`solvency.py` 添加安全数值处理辅助函数：

```python
def _safe_num(val) -> float:
    """安全提取数值，将 None/NaN 转为 0.0。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    return float(val)

def _is_valid(val: object) -> bool:
    """判断数值是否有效（非 None、非 NaN、非 0）。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return val != 0
```

替换所有 `.get(..., 0) or 0` 模式为 `_safe_num()` / `_is_valid()`。

### 效果

- 修复前：净债务/EBITDA = `nan` → 🔴
- 修复后：净债务/EBITDA = `-0.44 ~ -0.69` → 🟢（负值 = 净现金，财务极优）

---

## 问题 4: LLM 误读白酒指标

### 症状

LLM 将低存货周转率解释为"库存积压风险"，将高分红导致的低留存现金流比率为"现金流紧张"。

### 根因

Prompt 缺乏行业特殊性引导，LLM 机械套用通用阈值做定性判断。

### 修复方案

| 文件 | 修复内容 |
|------|----------|
| `fa_analyze.md` | 添加"行业特殊性提醒"段落，强制白酒行业指标适配 |
| `ia_analyze.md` | 添加"行业特殊性提醒"段落，Chapter 5 强制红灯指标行业适配 |

---

## 关联

- `docs/incidents/002-report-accuracy-20260526.md` — 报告准确性复盘（第一层问题）
- `docs/adr/0003-dual-threshold-scoring.md` — 双阈值评分模型设计
