"""茅台(600519)指标验证脚本 — 输出所有计算公式、参数、结果。"""

import sys
import json
import traceback
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd

sys.path.insert(0, "src")

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.metrics.solvency import calc_solvency
from finance_agent.metrics.profitability import calc_profitability
from finance_agent.metrics.efficiency import calc_efficiency
from finance_agent.metrics.cashflow import calc_cashflow
from finance_agent.metrics.dupont import calc_dupont
from finance_agent.metrics.traffic_light import assess_traffic_lights, compute_health_score

STOCK = "600519"

client = AKShareClient()

print("=" * 60)
print(f"正在拉取 {STOCK} 贵州茅台 的财务数据...")
print("=" * 60)

# 拉取数据
bs = client.fetch_balance_sheet(STOCK)
inc = client.fetch_income_statement(STOCK)
cf = client.fetch_cash_flow(STOCK)
ind = client.fetch_indicators(STOCK, start_year="2020")

print(f"\n资产负债表: {len(bs)} 年")
print(f"利润表: {len(inc)} 年")
print(f"现金流量表: {len(cf)} 年")
print(f"预计算指标: {len(ind)} 年")

# 打印列名用于调试
print(f"\n资产负债表列名: {list(bs.columns)}")
print(f"\n利润表列名: {list(inc.columns)}")
print(f"\n现金流量表列名列: {list(cf.columns)}")

# 打印关键原始数据
print("\n" + "=" * 60)
print("原始数据 (最近一年)")
print("=" * 60)

row_bs = bs.iloc[0]
row_is = inc.iloc[0]
row_cf = cf.iloc[0]

print(f"\n--- 资产负债表 ({row_bs.get('报告日', 'N/A')}) ---")
for col in ["资产总计", "负债合计", "所有者权益(或股东权益)合计", "流动资产合计", "流动负债合计",
             "存货", "货币资金", "短期借款", "长期借款", "应付债券", "一年内到期的非流动负债",
             "累计折旧", "应付账款"]:
    val = row_bs.get(col, "N/A")
    print(f"  {col}: {val}")

print(f"\n--- 利润表 ({row_is.get('报告日', 'N/A')}) ---")
for col in ["营业收入", "营业成本", "净利润", "利润总额", "所得税费用", "利息费用",
             "销售费用", "管理费用", "研发费用", "财务费用"]:
    val = row_is.get(col, "N/A")
    print(f"  {col}: {val}")

print(f"\n--- 现金流量表 ({row_cf.get('报告日', 'N/A')}) ---")
for col in ["经营活动产生的现金流量净额",
             "购建固定资产、无形资产和其他长期资产所支付的现金",
             "分配股利、利润或偿付利息所支付的现金"]:
    val = row_cf.get(col, "N/A")
    print(f"  {col}: {val}")

# 计算所有指标
print("\n" + "=" * 60)
print("计算指标结果")
print("=" * 60)

solvency = calc_solvency(bs, inc, ind)
profitability = calc_profitability(bs, inc, ind)
efficiency = calc_efficiency(bs, inc, ind)
cashflow = calc_cashflow(bs, inc, cf)
dupont = calc_dupont(bs, inc)

def fmt_val(v):
    if v is None:
        return "N/A"
    if isinstance(v, float):
        if abs(v) >= 1e8:
            return f"{v/1e8:.2f}亿"
        if abs(v) >= 1e4:
            return f"{v/1e4:.2f}万"
        return f"{v:.4f}"
    return str(v)

def print_metrics(name, data):
    print(f"\n## {name}")
    years = set()
    for v in data.values():
        years.update(v.keys())
    years = sorted(years, reverse=True)

    # header
    header = f"{'指标':<15}" + "".join(f"{y:>12}" for y in years)
    print(header)
    print("-" * len(header))
    for metric, vals in data.items():
        row = f"{metric:<15}" + "".join(f"{fmt_val(vals.get(y)):>12}" for y in years)
        print(row)

print_metrics("偿债能力 (Solvency)", solvency)
print_metrics("盈利能力 (Profitability)", profitability)
print_metrics("运营效率 (Efficiency)", efficiency)
print_metrics("现金流健康 (Cash Flow)", cashflow)

print(f"\n## 杜邦分解 (DuPont)")
for level in ["L1", "L2", "L3"]:
    print(f"\n### {level}")
    years = sorted(dupont[level].keys(), reverse=True)
    items = list(list(dupont[level].values())[0].keys())
    header = f"{'项目':<15}" + "".join(f"{y:>12}" for y in years)
    print(header)
    print("-" * len(header))
    for item in items:
        row_str = f"{item:<15}"
        for y in years:
            v = dupont[level][y].get(item, None)
            row_str += f"{fmt_val(v):>12}"
        print(row_str)

# 红黄绿灯
print(f"\n## 红黄绿灯 (Traffic Lights)")
all_metrics = {
    "solvency": solvency,
    "profitability": profitability,
    "efficiency": efficiency,
    "cashflow": cashflow,
}
lights = assess_traffic_lights(all_metrics)
for dim, dim_data in lights.items():
    print(f"\n### {dim}")
    for metric, year_data in dim_data.items():
        parts = []
        for y in sorted(year_data.keys(), reverse=True):
            entry = year_data[y]
            if entry["final"]:
                color = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(entry["final"], "?")
                parts.append(f"{y}:{color}")
        print(f"  {metric:<15} {' '.join(parts)}")

# 健康度评分
years_list = sorted(set().union(*(d.keys() for dim in all_metrics.values() for d in dim.values())), reverse=True)
print(f"\n## 健康度评分")
for y in years_list:
    score = compute_health_score(lights, y)
    dim_parts = " | ".join(f"{k}={v:.1f}" for k, v in score["dimensions"].items())
    print(f"  {y}: 总分={score['total']:.1f} ({score['rating']}) — {dim_parts}")

# 导出 JSON 供后续生成 MD 使用
output = {
    "stock": STOCK,
    "solvency": solvency,
    "profitability": profitability,
    "efficiency": efficiency,
    "cashflow": cashflow,
    "dupont": dupont,
    "lights": lights,
}

# 把 NaN 转成 None
def clean(obj):
    if isinstance(obj, float) and pd.isna(obj):
        return None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    return obj

output = clean(output)

with open("reports/600519_metrics_raw.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)

print(f"\n\n原始数据已保存到 reports/600519_metrics_raw.json")
