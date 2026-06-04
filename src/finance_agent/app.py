"""Gradio frontend with search, export, and error handling."""

from __future__ import annotations

import gradio as gr

from finance_agent.app_search import search_stocks
from finance_agent.graph import build_graph

graph = build_graph()


def analyze(
    stock_code: str,
    analysis_type: str,
    peer_codes: str,
    enable_web_search: bool,
) -> tuple[str, str | None, str | None, dict, dict]:
    """Run analysis and return report + file paths."""
    if not stock_code or not stock_code.strip():
        return (
            "❌ 请输入股票代码",
            None,
            None,
            gr.update(visible=False),
            gr.update(visible=False),
        )

    peers = [c.strip() for c in peer_codes.split(",") if c.strip()] or None

    try:
        result = graph.invoke(
            {
                "stock_code": stock_code.strip(),
                "analysis_type": analysis_type,
                "peer_codes": peers,
                "enable_web_search": enable_web_search,
            }
        )
    except ValueError as e:
        return (
            f"❌ 数据错误：{e}",
            None,
            None,
            gr.update(visible=False),
            gr.update(visible=False),
        )
    except Exception as e:
        return (
            f"❌ 分析失败：{e}",
            None,
            None,
            gr.update(visible=False),
            gr.update(visible=False),
        )

    report = (
        result.get("final_report")
        or result.get("financial_report")
        or result.get("investment_report")
        or "分析完成（无报告内容）"
    )

    file_paths = result.get("file_paths") or {}
    docx_path = file_paths.get("docx")
    pptx_path = file_paths.get("pptx")

    return (
        report,
        docx_path,
        pptx_path,
        gr.update(visible=bool(docx_path)),
        gr.update(visible=bool(pptx_path)),
    )


def on_search(query: str) -> gr.Dropdown:
    """Update dropdown choices based on search query."""
    if not query or len(query) < 1:
        return gr.update(choices=[])  # pyrefly: ignore[bad-return]
    matches = search_stocks(query)
    choices = dict(matches)
    return gr.update(choices=choices)  # pyrefly: ignore[bad-return]


# ── Build Gradio UI ──
with gr.Blocks(title="金融AI分析报告系统") as demo:
    gr.Markdown("# 金融AI分析报告系统")

    with gr.Row():
        # ── Left column: inputs ──
        with gr.Column(scale=1):
            search_box = gr.Textbox(
                label="搜索股票（名称或代码）",
                placeholder="输入股票名称或代码，如 茅台 或 600519",
            )
            stock_dropdown = gr.Dropdown(
                label="选择股票",
                choices=[],
                interactive=True,
                allow_custom_value=True,
            )
            stock_code = gr.Textbox(
                label="股票代码",
                placeholder="例：600519",
            )
            analysis_type = gr.Dropdown(
                choices=["financial", "investment", "comprehensive"],
                value="comprehensive",
                label="分析类型",
            )
            peer_codes = gr.Textbox(
                label="对标股票（可选，逗号分隔）",
                placeholder="例：000858,000568",
            )
            enable_web_search = gr.Checkbox(
                label="启用实时事件搜索（WebSearch）",
                value=True,
                info="开启后优先通过网络搜索获取最新事件，失败时自动降级到预构建库。关闭后只读取本地预构建事件。",
            )
            submit_btn = gr.Button("开始分析", variant="primary")

        # ── Right column: outputs ──
        with gr.Column(scale=2):
            output = gr.Markdown(label="分析报告")
            with gr.Row():
                docx_download = gr.File(
                    label="下载 Word 报告",
                    visible=False,
                )
                pptx_download = gr.File(
                    label="下载 PPT 报告",
                    visible=False,
                )

    # Wire up search
    search_box.change(
        fn=on_search,
        inputs=search_box,
        outputs=stock_dropdown,
    )
    stock_dropdown.change(
        fn=lambda x: x,
        inputs=stock_dropdown,
        outputs=stock_code,
    )

    # Wire up analysis
    submit_btn.click(
        fn=analyze,
        inputs=[stock_code, analysis_type, peer_codes, enable_web_search],
        outputs=[
            output,
            docx_download,
            pptx_download,
            docx_download,
            pptx_download,
        ],
        show_progress="full",
    )


def main() -> None:
    demo.launch()


if __name__ == "__main__":
    main()
