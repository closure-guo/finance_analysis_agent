"""Gradio frontend with search, export, and error handling."""

from __future__ import annotations

import traceback

import gradio as gr

from finance_agent.app_search import search_stocks
from finance_agent.graph import build_graph

graph = build_graph()

# ── Theme ──
CUSTOM_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.blue,
    secondary_hue=gr.themes.colors.slate,
    neutral_hue=gr.themes.colors.slate,
).set(
    button_primary_background_fill="*primary_500",
    button_primary_background_fill_hover="*primary_400",
    block_title_text_color="*primary_600",
    border_color_primary="*primary_200",
    table_even_background_fill="*neutral_50",
    table_odd_background_fill="white",
)

# ── Custom CSS ──
# Color palette (blue-500 base: #3b82f6)
# primary-50=#eff6ff, primary-100=#dbeafe, primary-200=#bfdbfe,
# primary-300=#93c5fd, primary-500=#3b82f6, primary-600=#2563eb, primary-700=#1d4ed8
# neutral-400=#9ca3af
CUSTOM_CSS = """
/* ── Section labels ── */
.section-label {
    color: #2563eb !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.03em;
    margin-bottom: 0.25rem;
    border-bottom: 1px solid #bfdbfe;
    padding-bottom: 0.25rem;
}

/* ── Report area ── */
.report-area {
    min-height: 400px;
    max-height: 75vh;
    overflow-y: auto;
}

/* ── Report tables ── */
.report-area table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin: 0.75rem 0 !important;
    font-size: 0.85rem !important;
}
.report-area th {
    background: #dbeafe !important;
    color: #1d4ed8 !important;
    font-weight: 600 !important;
    padding: 8px 12px !important;
    text-align: left !important;
    border-bottom: 2px solid #93c5fd !important;
}
.report-area td {
    padding: 6px 12px !important;
    border-bottom: 1px solid #e5e7eb !important;
}
.report-area tr:hover td {
    background: #eff6ff !important;
}

/* ── Download row spacing ── */
.download-row {
    margin-top: 0.75rem;
}

/* ── Disclaimer ── */
.disclaimer {
    text-align: center;
    color: #9ca3af !important;
    font-size: 0.8rem !important;
    margin-top: 1.5rem;
}
"""


def analyze(
    stock_code: str,
    analysis_type: str,
    peer_codes: str,
    enable_web_search: bool,
    progress: gr.Progress | None = None,
) -> tuple:
    """Run analysis and return report + file paths."""
    _progress = progress or gr.Progress(tracking=False)
    if not stock_code or not stock_code.strip():
        return (
            "❌ 请输入股票代码",
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )

    peers = [c.strip() for c in (peer_codes or "").split(",") if c.strip()] or None

    try:
        _progress(0.1, desc="正在获取财务数据...")
        result = graph.invoke(
            {
                "stock_code": stock_code.strip(),
                "analysis_type": analysis_type,
                "peer_codes": peers,
                "enable_web_search": enable_web_search,
            }
        )
        _progress(0.95, desc="分析完成，正在生成报告...")
    except ValueError as e:
        return (
            f"❌ 数据错误：{e}",
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )
    except Exception as e:
        traceback.print_exc()
        return (
            f"❌ 分析失败：{e}",
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
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
        gr.update(value=docx_path, visible=bool(docx_path)),
        gr.update(value=pptx_path, visible=bool(pptx_path)),
    )


def _extract_code(selected: str) -> str:
    """Extract stock code from dropdown label like '贵州茅台 (600519)'."""
    if not selected:
        return ""
    parts = selected.rsplit("(", 1)
    if len(parts) == 2:
        return parts[1].rstrip(")")
    return selected.strip()


def on_search(query: str):
    """Update dropdown with search results and auto-select the first match."""
    if not query or len(query) < 1:
        return gr.update(choices=[]), gr.update(value="")
    matches = search_stocks(query)
    labels = [label for label, _ in matches]
    first_label = labels[0] if labels else ""
    first_code = _extract_code(first_label)
    return gr.update(choices=labels, value=first_label), gr.update(value=first_code)


# ── Build Gradio UI ──
with gr.Blocks(title="金融AI分析报告系统") as demo:
    gr.Markdown("# 金融AI分析报告系统\nA股上市公司智能财务分析与投资评估平台")

    with gr.Row():
        # ── Left column: inputs ──
        with gr.Column(scale=1):
            gr.HTML('<div class="section-label">股票选择</div>')
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

            gr.HTML('<div class="section-label">分析配置</div>')
            analysis_type = gr.Dropdown(
                choices=[
                    ("财务分析", "financial"),
                    ("投资分析", "investment"),
                    ("综合分析（财务+投资）", "comprehensive"),
                ],
                value="comprehensive",
                label="分析类型",
            )

            with gr.Accordion("高级选项", open=False):
                peer_codes = gr.Textbox(
                    label="对标股票（可选，逗号分隔）",
                    placeholder="例：000858,000568",
                )
                enable_web_search = gr.Checkbox(
                    label="启用实时事件搜索（WebSearch）",
                    value=True,
                    info="开启后优先通过网络搜索获取最新事件，失败时自动降级到预构建库。"
                    "关闭后只读取本地预构建事件。",
                )

            submit_btn = gr.Button("开始分析", variant="primary")

        # ── Right column: outputs ──
        with gr.Column(scale=2):
            output = gr.Markdown(
                value="等待分析结果...\n\n> ⏳ 分析生成通常需要 **2-5 分钟**，请耐心等待",
                elem_classes="report-area",
            )
            with gr.Row(elem_classes="download-row"):
                docx_download = gr.File(
                    label="下载 Word 报告",
                    visible=False,
                )
                pptx_download = gr.File(
                    label="下载 PPT 报告",
                    visible=False,
                )

    # ── Disclaimer ──
    gr.Markdown(
        "⚠️ 报告由AI自动生成，仅供参考，不构成投资建议",
        elem_classes="disclaimer",
    )

    # Wire up search
    search_box.change(
        fn=on_search,
        inputs=search_box,
        outputs=[stock_dropdown, stock_code],
    )
    stock_dropdown.change(
        fn=_extract_code,
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
        ],
    )


def main() -> None:
    demo.queue(max_size=3)
    demo.launch(theme=CUSTOM_THEME, css=CUSTOM_CSS)


if __name__ == "__main__":
    main()
