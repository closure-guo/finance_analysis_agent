"""Gradio 前端入口"""

import gradio as gr

from finance_agent.graph import build_graph

graph = build_graph()


def analyze(stock_code: str, analysis_type: str, peer_codes: str) -> str:
    peers = [c.strip() for c in peer_codes.split(",") if c.strip()] or None

    result = graph.invoke({
        "stock_code": stock_code,
        "analysis_type": analysis_type,
        "peer_codes": peers,
    })

    return result.get("final_report") or result.get("financial_report") or result.get("investment_report") or "分析完成（stub）"


def main():
    with gr.Blocks(title="金融AI分析报告系统") as demo:
        gr.Markdown("# 金融AI分析报告系统")

        with gr.Row():
            stock_code = gr.Textbox(label="股票代码", placeholder="例：600519")
            analysis_type = gr.Dropdown(
                choices=["financial", "investment", "comprehensive"],
                value="financial",
                label="分析类型",
            )
            peer_codes = gr.Textbox(label="对标股票（可选，逗号分隔）", placeholder="例：000858,000568")

        submit_btn = gr.Button("开始分析", variant="primary")
        output = gr.Markdown(label="分析报告")

        submit_btn.click(
            fn=analyze,
            inputs=[stock_code, analysis_type, peer_codes],
            outputs=output,
        )

    demo.launch()


if __name__ == "__main__":
    main()
