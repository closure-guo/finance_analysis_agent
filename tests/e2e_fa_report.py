"""端到端测试：真实 AKShare 数据 + LLM 生成 FA 报告。

运行方式：
    export Deepseek-Api-Key=your_key
    uv run python tests/e2e_fa_report.py
"""

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.nodes.compute import compute_metrics
from finance_agent.nodes.fa import fa_analyze

STOCK_CODE = "600519"  # 贵州茅台


def main():
    print(f"=== 端到端测试：{STOCK_CODE} 财务分析 ===\n")

    # 1. 拉取真实数据
    print("[1/4] 拉取 AKShare 数据...")
    ak = AKShareClient()
    bs = ak.fetch_balance_sheet(STOCK_CODE)
    inc = ak.fetch_income_statement(STOCK_CODE)
    cf = ak.fetch_cash_flow(STOCK_CODE)
    try:
        ind = ak.fetch_indicators(STOCK_CODE)
    except Exception:
        ind = None
    try:
        quote = ak.fetch_stock_quote(STOCK_CODE)
    except Exception:
        quote = {}
    try:
        industry = ak.fetch_industry(STOCK_CODE)
    except Exception:
        industry = {}

    print(f"  资产负债表: {len(bs)} 年")
    print(f"  利润表: {len(inc)} 年")
    print(f"  现金流量表: {len(cf)} 年")

    # 2. 计算指标
    print("\n[2/4] 计算 20 指标 + 杜邦 + 红黄绿灯...")
    state = {
        "stock_code": STOCK_CODE,
        "balance_sheet": bs,
        "income_statement": inc,
        "cash_flow_statement": cf,
        "financial_indicators": ind,
        "stock_quote": quote,
        "industry_info": industry,
        "peer_financials": None,
    }
    computed = compute_metrics(state)
    state.update(computed)

    score = state.get("health_score", {})
    print(f"  健康度评分: {score.get('total', 'N/A')}/100 ({score.get('rating', 'N/A')})")
    print(f"  异常数: {len(state.get('anomalies', []))}")

    # 3. 调 LLM 生成报告
    print("\n[3/4] 调用 LLM 生成财务分析报告（双阶段）...")
    result = fa_analyze(state)

    # 4. 输出报告 + 保存到文件
    print("\n[4/4] 报告生成完成\n")
    report = result["financial_report"]

    from pathlib import Path
    out_path = Path(__file__).parent / "e2e" / f"report_{STOCK_CODE}_fa.md"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"报告已保存到: {out_path}")
    print(f"报告长度: {len(report)} 字符\n")

    print("=" * 60)
    print(report[:3000])
    if len(report) > 3000:
        print(f"\n... (共 {len(report)} 字符)")
    print("=" * 60)

    # 验证报告包含 8 章关键内容
    checks = {
        "封面": "贵州茅台" in report or STOCK_CODE in report,
        "执行摘要": "执行摘要" in report,
        "核心指标": "偿债" in report or "盈利" in report,
        "杜邦": "杜邦" in report or "ROE" in report,
        "风险提示": "风险" in report,
        "结论": "评级" in report or "健康" in report or "关注" in report,
        "免责声明": "免责声明" in report,
    }

    print("\n验证结果：")
    all_pass = True
    for name, ok in checks.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print("\n✅ 端到端测试通过！")
    else:
        print("\n❌ 部分检查未通过，请检查报告内容。")

    return all_pass


if __name__ == "__main__":
    main()
