"""Gradio frontend with 5-layer deep-research progress UI."""

from __future__ import annotations

import traceback

import gradio as gr

from finance_agent.app_search import search_stocks
from finance_agent.graph import build_5layer_graph

graph = build_5layer_graph()

# ── 5 层架构节点 → 显示层映射 ──
LAYER_STEPS: list[tuple[str, str, str]] = [
    ("check_cache", "PREP", "数据准备"),
    ("fetch_data", "PREP", "获取财务数据"),
    ("validate_financials", "PREP", "勾稽校验"),
    ("compute_metrics", "PREP", "指标计算"),
    ("technical_analyst", "Layer I", "技术面分析"),
    ("verify_citations", "校验", "引用校验"),
    ("bull_r1", "Layer II", "看多辩论 R1"),
    ("bear_r1", "Layer II", "看空辩论 R1"),
    ("bull_r2", "Layer II", "看多辩论 R2"),
    ("bear_r2", "Layer II", "看空辩论 R2"),
    ("research_manager", "Layer II", "研究结论"),
    ("trader", "Layer III", "交易决策"),
    ("aggressive_r1", "Layer IV", "激进风控 R1"),
    ("conservative_r1", "Layer IV", "保守风控 R1"),
    ("neutral_r1", "Layer IV", "中性风控 R1"),
    ("aggressive_r2", "Layer IV", "激进风控 R2"),
    ("conservative_r2", "Layer IV", "保守风控 R2"),
    ("neutral_r2", "Layer IV", "中性风控 R2"),
    ("risk_judge", "Layer IV", "风控裁决"),
    ("fund_manager", "Layer V", "基金经理审批"),
    ("generate_report", "报告", "报告生成"),
    ("generate_file", "报告", "文件导出"),
]

_NODE_INDEX: dict[str, int] = {node: i for i, (node, _, _) in enumerate(LAYER_STEPS)}
_ALL_NODES: set[str] = {node for node, _, _ in LAYER_STEPS}

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

/* ── Progress panel ── */
.progress-panel {
    background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%) !important;
    border: 1px solid #bfdbfe !important;
    border-radius: 10px !important;
    padding: 16px 20px !important;
    max-height: 60vh;
    overflow-y: auto;
}
.progress-panel h2 {
    font-size: 1.05rem !important;
    color: #1d4ed8 !important;
    border-bottom: 2px solid #93c5fd;
    padding-bottom: 0.5rem;
    margin-bottom: 0.75rem !important;
}
.progress-panel h3 {
    font-size: 0.9rem !important;
    color: #1e40af !important;
    margin: 0.75rem 0 0.35rem 0 !important;
    padding-left: 4px;
    border-left: 3px solid #3b82f6;
    padding-left: 8px;
}
.progress-panel ul {
    list-style: none !important;
    padding-left: 12px !important;
    margin: 0.15rem 0 !important;
}
.progress-panel li {
    margin: 0.2rem 0 !important;
    font-size: 0.85rem !important;
    line-height: 1.5;
    color: #475569;
}
.progress-panel li::marker {
    content: "";
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


# ── Progress / state formatting helpers ──


def _format_progress(completed: set[str], current: str | None) -> str:
    """Format the progress panel markdown with layer groupings."""
    total = len(LAYER_STEPS)
    done = len(completed & _ALL_NODES)
    lines = [f"## 📊 分析进度 ({done}/{total})\n"]

    # Group steps by layer
    prev_layer = None
    for node, layer, desc in LAYER_STEPS:
        if layer != prev_layer:
            if prev_layer is not None:
                lines.append("")  # blank line between groups
            # Determine layer status
            layer_nodes = [n for n, lvl, _ in LAYER_STEPS if lvl == layer]
            layer_done = all(n in completed for n in layer_nodes)
            layer_running = any(n == current for n in layer_nodes)
            if layer_done:
                lines.append(f"### ✅ {layer}")
            elif layer_running:
                lines.append(f"### ⏳ {layer}")
            else:
                lines.append(f"### ⏸️ {layer}")
            prev_layer = layer

        if node in completed:
            icon = "✅"
        elif node == current:
            icon = "⏳"
        else:
            icon = "⏸️"
        lines.append(f"- {icon} {desc}")

    return "\n".join(lines)


def _format_analyst_reports(state: dict) -> str:
    """Format analyst reports for the accordion."""
    reports = state.get("analyst_reports") or {}
    if not reports:
        return "*等待分析师团队产出...*"
    lines = []
    for name, report in reports.items():
        if hasattr(report, "summary"):
            lines.append(f"### {name}\n\n{report.summary}\n")
            if hasattr(report, "key_findings") and report.key_findings:
                lines.append("**关键发现：**")
                for f in report.key_findings:
                    lines.append(f"- {f}")
        elif isinstance(report, dict):
            lines.append(f"### {name}\n\n{report.get('summary', '')}\n")
    return "\n".join(lines) if lines else "*无数据*"


def _format_debate(state: dict) -> str:
    """Format debate history."""
    history = state.get("debate_history") or []
    if not history:
        return "*等待多空辩论...*"
    lines = []
    for msg in history:
        if hasattr(msg, "role"):
            lines.append(f"**{msg.role}** (R{msg.round}): {msg.content}\n")
        elif isinstance(msg, dict):
            lines.append(
                f"**{msg.get('role', '?')}** (R{msg.get('round', '?')}): {msg.get('content', '')}\n"
            )
    return "\n".join(lines)


def _format_decision(state: dict) -> str:
    """Format trade decision."""
    decision = state.get("final_trade_decision") or state.get("trader_plan")
    if not decision:
        return "*等待交易决策...*"
    if hasattr(decision, "action"):
        return (
            f"- **方向**: {decision.action}\n"
            f"- **置信度**: {decision.confidence:.0%}\n"
            f"- **理由**: {decision.reasoning}"
        )
    elif isinstance(decision, dict):
        return (
            f"- **方向**: {decision.get('action', 'N/A')}\n"
            f"- **置信度**: {decision.get('confidence', 0):.0%}\n"
            f"- **理由**: {decision.get('reasoning', '')}"
        )
    return "*无数据*"


def _format_risk_debate(state: dict) -> str:
    """Format risk debate."""
    history = state.get("risk_debate_history") or []
    if not history:
        return "*等待风控辩论...*"
    lines = []
    for msg in history:
        if hasattr(msg, "role"):
            lines.append(f"**{msg.role}**: {msg.content}\n")
        elif isinstance(msg, dict):
            lines.append(f"**{msg.get('role', '?')}**: {msg.get('content', '')}\n")
    return "\n".join(lines)


def _format_fund_manager(state: dict) -> str:
    """Format fund manager decision."""
    decision = state.get("fund_manager_decision")
    if not decision:
        return "*等待基金经理审批...*"
    return f"**决策**: {decision}"


def _merge_update(accumulated: dict, node_name: str, update) -> None:
    """Merge a node's update dict into the accumulated state, respecting reducers.

    ``stream_mode="updates"`` only delivers per-node deltas, so we mimic the
    LangGraph reducers locally to keep a full picture for the formatters.
    """
    if not isinstance(update, dict):
        return
    for key, value in update.items():
        if key == "analyst_reports":
            existing = accumulated.get(key) or {}
            if isinstance(value, dict):
                accumulated[key] = {**existing, **value}
            else:
                accumulated[key] = value
        elif key in ("debate_history", "risk_debate_history"):
            existing = accumulated.get(key) or []
            if isinstance(value, list):
                accumulated[key] = existing + value
            else:
                accumulated[key] = value
        else:
            accumulated[key] = value


def _next_pending(completed: set[str]) -> str | None:
    """Return the first LAYER_STEPS node not yet completed, or None if all done."""
    for node, _, _ in LAYER_STEPS:
        if node not in completed:
            return node
    return None


def _step_desc(node: str | None) -> str:
    """Human description for the currently-running node."""
    if not node:
        return "分析完成"
    for n, layer, desc in LAYER_STEPS:
        if n == node:
            return f"{layer} · {desc}"
    return "分析中..."


def _progress_frac(completed: set[str]) -> float:
    """Map completed-step count to a 0-0.95 fraction for gr.Progress."""
    if not LAYER_STEPS:
        return 0.0
    return min(0.95, len(completed) / len(LAYER_STEPS))


# ── Empty-state placeholders for intermediate panels ──
_EMPTY_ANALYST = _format_analyst_reports({})
_EMPTY_DEBATE = _format_debate({})
_EMPTY_DECISION = _format_decision({})
_EMPTY_RISK = _format_risk_debate({})
_EMPTY_FM = _format_fund_manager({})


def analyze(
    stock_dropdown: str,
    stock_code: str,
    analysis_type: str,
    api_key: str,
    peer_codes: str,
    enable_web_search: bool,
    progress: gr.Progress | None = None,
):
    """Run 5-layer analysis as a generator, streaming progress to the UI."""
    _progress = progress or gr.Progress()

    # ── Input validation ──
    if not stock_code or not stock_code.strip():
        yield (
            "## 分析进度\n\n❌ **请输入股票代码**",
            _EMPTY_ANALYST,
            _EMPTY_DEBATE,
            _EMPTY_DECISION,
            _EMPTY_RISK,
            _EMPTY_FM,
            "❌ 请输入股票代码",
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )
        return
    if not api_key or not api_key.strip():
        raise gr.Error("请先输入 DeepSeek API Key")

    stock_code = stock_code.strip()
    stock_name = _extract_name(stock_dropdown) or stock_code
    peers = [c.strip() for c in (peer_codes or "").split(",") if c.strip()] or None

    initial_state = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "analysis_type": analysis_type or "comprehensive",
        "peer_codes": peers,
        "enable_web_search": enable_web_search,
        "api_key": api_key.strip() or None,
    }

    completed: set[str] = set()
    accumulated: dict = dict(initial_state)

    # ── Initial yield: roadmap with first step marked as running ──
    first_node = LAYER_STEPS[0][0]
    _progress(0.02, desc="启动 5 层架构分析...")
    yield (
        _format_progress(completed, first_node),
        _EMPTY_ANALYST,
        _EMPTY_DEBATE,
        _EMPTY_DECISION,
        _EMPTY_RISK,
        _EMPTY_FM,
        "⏳ 分析进行中...\n\n> 5 层架构分析通常需要数分钟，请耐心等待。",
        gr.update(value=None, visible=False),
        gr.update(value=None, visible=False),
    )

    # ── Stream node updates ──
    try:
        for chunk in graph.stream(
            initial_state,
            config={"recursion_limit": 100},
            stream_mode="updates",
        ):
            has_update = False
            for node_name, update in chunk.items():
                _merge_update(accumulated, node_name, update)
                if node_name in _NODE_INDEX:
                    idx = _NODE_INDEX[node_name]
                    # Mark every step up to this node as done. This gracefully
                    # covers parallel siblings and skipped nodes (e.g. fetch_data
                    # on cache HIT) so the progress bar never stalls.
                    for i in range(idx + 1):
                        completed.add(LAYER_STEPS[i][0])
                    has_update = True
                elif isinstance(update, dict) and update:
                    has_update = True

            # Skip no-op passthrough nodes to avoid flicker.
            if not has_update:
                continue

            current = _next_pending(completed)
            _progress(_progress_frac(completed), desc=_step_desc(current))

            # Update stock_name from fetched data if it was a fallback
            if accumulated.get("stock_name") in (None, "", stock_code):
                quote = accumulated.get("stock_quote") or {}
                info = accumulated.get("industry_info") or {}
                fetched_name = quote.get("name") or info.get("name")
                if fetched_name:
                    accumulated["stock_name"] = fetched_name

            file_paths = accumulated.get("file_paths") or {}
            docx_path = file_paths.get("docx")
            pptx_path = file_paths.get("pptx")
            report_so_far = accumulated.get("final_report") or "⏳ 分析进行中..."

            yield (
                _format_progress(completed, current),
                _format_analyst_reports(accumulated),
                _format_debate(accumulated),
                _format_decision(accumulated),
                _format_risk_debate(accumulated),
                _format_fund_manager(accumulated),
                report_so_far,
                gr.update(value=docx_path, visible=bool(docx_path)),
                gr.update(value=pptx_path, visible=bool(pptx_path)),
            )
    except ValueError as e:
        yield (
            _format_progress(completed, None),
            _format_analyst_reports(accumulated),
            _format_debate(accumulated),
            _format_decision(accumulated),
            _format_risk_debate(accumulated),
            _format_fund_manager(accumulated),
            f"❌ 数据错误：{e}",
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )
        return
    except Exception as e:
        traceback.print_exc()
        yield (
            _format_progress(completed, None),
            _format_analyst_reports(accumulated),
            _format_debate(accumulated),
            _format_decision(accumulated),
            _format_risk_debate(accumulated),
            _format_fund_manager(accumulated),
            f"❌ 分析失败：{e}",
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )
        return

    # ── Final yield ──
    final_report = accumulated.get("final_report")
    if final_report:
        completed_final = _ALL_NODES
    else:
        # Early termination (e.g. validation FAIL short-circuited to END).
        completed_final = completed
        if accumulated.get("validation_result") == "FAIL":
            warnings = accumulated.get("validation_warnings") or []
            warn_text = "\n".join(f"- {w}" for w in warnings) if warnings else "- 未知问题"
            final_report = (
                "❌ **勾稽校验未通过，分析已终止。**\n\n"
                f"**校验问题：**\n{warn_text}\n\n"
                "请检查财务数据或更换股票后重试。"
            )
        else:
            final_report = "❌ 分析未完成，未生成报告。请查看日志或重试。"

    file_paths = accumulated.get("file_paths") or {}
    docx_path = file_paths.get("docx")
    pptx_path = file_paths.get("pptx")

    _progress(1.0, desc="分析完成")
    yield (
        _format_progress(completed_final, None),
        _format_analyst_reports(accumulated),
        _format_debate(accumulated),
        _format_decision(accumulated),
        _format_risk_debate(accumulated),
        _format_fund_manager(accumulated),
        final_report,
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


def _extract_name(selected: str) -> str:
    """Extract stock name from dropdown label like '贵州茅台 (600519)'."""
    if not selected:
        return ""
    parts = selected.rsplit("(", 1)
    if len(parts) == 2:
        return parts[0].strip()
    return ""


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
            api_key_input = gr.Textbox(
                label="DeepSeek API Key",
                type="password",
                placeholder="sk-...",
                info="你的 Key 仅用于本次请求，不会存储或发送给第三方。",
            )
            analysis_type = gr.Dropdown(
                choices=[("5层架构综合分析（财务+投资+风控）", "comprehensive")],
                value="comprehensive",
                label="分析类型",
                interactive=False,
                info="5 层架构为唯一分析模式",
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
            # Progress panel
            progress_md = gr.Markdown(
                value=_format_progress(set(), None),
                elem_classes="progress-panel",
            )

            # Intermediate results (accordions, initially open for live streaming)
            with gr.Accordion("📊 分析师团队报告", open=True):
                analyst_md = gr.Markdown(value=_EMPTY_ANALYST)
            with gr.Accordion("⚔️ 多空辩论", open=True):
                debate_md = gr.Markdown(value=_EMPTY_DEBATE)
            with gr.Accordion("🎯 交易决策", open=True):
                decision_md = gr.Markdown(value=_EMPTY_DECISION)
            with gr.Accordion("🛡️ 风控辩论", open=True):
                risk_md = gr.Markdown(value=_EMPTY_RISK)
            with gr.Accordion("📋 基金经理决策", open=True):
                fm_md = gr.Markdown(value=_EMPTY_FM)

            # Final report
            output = gr.Markdown(
                value="等待分析结果...\n\n> ⏳ 分析生成通常需要 **2-5 分钟**，请耐心等待",
                elem_classes="report-area",
            )
            gr.HTML(
                value=(
                    '<button onclick="copyReport()" '
                    'style="margin-top:0.5rem;padding:6px 16px;border:1px solid #bfdbfe;'
                    "border-radius:6px;background:#eff6ff;color:#1d4ed8;font-size:0.85rem;"
                    'cursor:pointer;transition:all .2s;" '
                    "onmouseover=\"this.style.background='#dbeafe'\" "
                    "onmouseout=\"this.style.background='#eff6ff'\">"
                    "&#x1f4cb; 复制报告全文</button>"
                    "<script>"
                    "function copyReport(){"
                    "  var el=document.querySelector('.report-area');"
                    "  if(!el){alert('未找到报告内容');return}"
                    "  navigator.clipboard.writeText(el.innerText).then(function(){"
                    "    var btn=document.querySelector('button[onclick=\"copyReport()\"]');"
                    "    var orig=btn.innerHTML;"
                    "    btn.innerHTML='&#x2705; 已复制！';"
                    "    btn.style.background='#d1fae5';"
                    "    btn.style.borderColor='#6ee7b7';"
                    "    btn.style.color='#065f46';"
                    "    setTimeout(function(){"
                    "      btn.innerHTML=orig;"
                    "      btn.style.background='#eff6ff';"
                    "      btn.style.borderColor='#bfdbfe';"
                    "      btn.style.color='#1d4ed8';"
                    "    },2000);"
                    "  }).catch(function(){alert('复制失败，请手动选择文本复制')});"
                    "}"
                    "</script>"
                ),
            )
            with gr.Row(elem_classes="download-row"):
                docx_download = gr.DownloadButton(
                    label="下载 Word 报告",
                    visible=False,
                )
                pptx_download = gr.DownloadButton(
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
        inputs=[
            stock_dropdown,
            stock_code,
            analysis_type,
            api_key_input,
            peer_codes,
            enable_web_search,
        ],
        outputs=[
            progress_md,
            analyst_md,
            debate_md,
            decision_md,
            risk_md,
            fm_md,
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
