"""judge 标注材料提取（material.py）与 CSV 标注表 测试（fixtures 离线）。

覆盖：渲染 prompt 的【小节】切分、观测 input 各形态解析、维度摘要构建、
CSV 标注表生成与回读（measure.load_labeled_csv）。
"""

import json

from evals.judge_calibration.material import (
    CSV_HEADER,
    build_summary,
    detect_dimension,
    extract_sections,
    humanize_json_blocks,
    prompt_from_observation_input,
    sections_for_dimension,
    to_csv,
    to_xlsx,
)
from evals.judge_calibration.measure import load_labeled_csv, load_labeled_xlsx
from evals.judges import _render


class TestPromptParsing:
    def test_extract_sections_from_rendered_rubric(self):
        rendered = _render("report_relevance", {"query": "分析茅台", "report": "报告正文…"})
        sections = extract_sections(rendered, "report_relevance")
        assert sections.get("【用户查询】") == "分析茅台"
        # 尾部 rubric 指令（评估/只输出 JSON）被锚点截掉，只留材料本身
        assert sections.get("【分析报告】") == "报告正文…"

    def test_nested_markers_do_not_break_extraction(self):
        """回归（2026-09-08 实测）：analyst_reports/辩论正文嵌套【technical】【bull】等
        未知标记，不得被当作小节边界切断材料。"""
        rendered = _render(
            "consistency",
            {
                "analyst_reports": "【technical】MA5 走强\n【fundamental】ROE 32%",
                "research_manager_decision": "RM 偏多",
                "risk_judgment": "风险可控",
                "fund_manager_decision": "批准",
                "report_conclusion": "结论一致",
            },
        )
        sections = extract_sections(rendered, "consistency")
        # 嵌套标记保留在材料原文，不被误切为小节
        assert "【technical】MA5 走强" in sections.get("【分析师章节结论】")
        assert "【fundamental】ROE 32%" in sections.get("【分析师章节结论】")

    def test_sections_for_dimension_covers_all_dims(self):
        for dim in ("report_relevance", "debate_quality", "decision_grounding", "consistency"):
            assert sections_for_dimension(dim)  # 每个维度至少一个小节
        # decision_grounding 人审必须含交易决策小节
        assert "【交易决策】" in sections_for_dimension("decision_grounding")
        # v6：裁决的证据基础（风控指标 + 三方风险辩论）必须在人审材料里
        assert "【风控指标】" in sections_for_dimension("decision_grounding")
        assert "【风险辩论记录】" in sections_for_dimension("decision_grounding")
        assert "【多空辩论记录】" in sections_for_dimension("debate_quality")

    def test_prompt_from_observation_input_variants(self):
        # gateway 观测落库 input = {"messages": [{"role": "user", "content": ...}]}
        inp = {"messages": [{"role": "user", "content": "PROMPT"}]}
        assert prompt_from_observation_input(inp) == "PROMPT"
        # 直传形态
        assert prompt_from_observation_input({"content": "PROMPT"}) == "PROMPT"
        # JSON 字符串形态
        assert prompt_from_observation_input(json.dumps(inp)) == "PROMPT"
        # 取不到 → None（不崩）
        assert prompt_from_observation_input(None) is None
        assert prompt_from_observation_input("not-json") == "not-json"
        assert prompt_from_observation_input({"messages": []}) is None

    def test_detect_dimension_by_intro(self):
        # judge generation 观测名统一为 "judge"，须按 rubric 首句特征识别维度
        vars_all = {
            "query": "q",
            "report": "r",
            "debate_history": "d",
            "analyst_reports": "a",
            "research_manager_decision": "rm",
            "trade_decision": "td",
            "risk_judgment": "rj",
            "fund_manager_decision": "fm",
            "report_conclusion": "rc",
        }
        for dim in ("report_relevance", "debate_quality", "decision_grounding", "consistency"):
            assert detect_dimension(_render(dim, vars_all)) == dim
        assert detect_dimension(None) is None


class TestBuildSummary:
    def test_decision_grounding_summary_has_all_sections(self):
        rendered = _render(
            "decision_grounding",
            {
                "analyst_reports": "分析师A: ROE 15%、毛利率 45%",
                "research_manager_decision": "RM 倾向买入",
                "trade_decision": '{"action": "buy", "reasoning": "ROE 支撑"}',
            },
        )
        s = build_summary(rendered, "decision_grounding")
        assert "分析师A: ROE 15%" in s
        assert "RM 倾向买入" in s
        assert "buy" in s

    def test_missing_prompt_returns_hint(self):
        s = build_summary(None, "report_relevance")
        assert "材料缺失" in s

    def test_long_sections_truncated(self):
        rendered = _render("debate_quality", {"debate_history": "长" * 5000})
        s = build_summary(rendered, "debate_quality", limit=200)
        assert len(s) < 500

    def test_debate_summary_keeps_both_sides_tail(self):
        """回归（2026-09-08 实测）：辩论维度材料被 350 字符二次截断，只留 bull 开头、
        bear 回应被砍掉——标注人看不到交锋双方。辩论须按维度放大截断上限，
        完整呈现 judge 实际看到的输入（extract 已 4096 字节首尾保留）。"""
        debate = "bull 开场立场" + ("长内容" * 300) + "bear 针对 bull 逐条回应并引用数据反驳"
        rendered = _render("debate_quality", {"debate_history": debate})
        s = build_summary(rendered, "debate_quality")
        assert "bull 开场立场" in s
        assert "bear 针对 bull 逐条回应" in s  # 尾部未被 350 上限砍掉

    def test_no_redundant_preview_line(self):
        """回归（2026-09-09）：截取式「▼ 一句话」与正文完全重复、无信息量——已移除；
        材料回归「小节标题 + 完整原文」（agent 节保留分行摘要）。"""
        rendered = _render(
            "decision_grounding",
            {
                "analyst_reports": "分析师A: ROE 15%、毛利率 45%",
                "research_manager_decision": "RM 倾向买入",
                "trade_decision": '{"action": "buy"}',
            },
        )
        s = build_summary(rendered, "decision_grounding")
        assert "▼ 一句话：" not in s
        assert "分析师A: ROE 15%" in s  # 原文完整保留
        assert "RM 倾向买入" in s
        assert "action: buy" in s  # 交易决策 JSON 人读化后信息等价保留

    def test_analyst_section_lists_each_agent_summary(self):
        """回归（2026-09-08/2026-09-09）：分析师节只保留原文、按【agent】标记分行
        （内容与 judge 所见一致）。「▼ 各 agent 摘要」预览与原文完全重复、无信息量
        ——已移除（与 2026-09-09「截取式预览重复」同因）。"""
        rendered = _render(
            "consistency",
            {
                "analyst_reports": (
                    "【technical】技术面偏空，MACD 死叉反弹动能存疑\n"
                    "【macro】宏观数据缺失，定性判断中性\n"
                    "【fundamental】基本面优异但增速放缓\n"
                    "【sentiment】舆情偏多"
                ),
                "research_manager_decision": "RM 多空对峙",
                "risk_judgment": "watch",
                "fund_manager_decision": "approve",
                "report_conclusion": "维持 watch",
            },
        )
        s = build_summary(rendered, "consistency")
        analyst_block = s.split("【分析师章节结论】", 1)[1].split("【Research Manager", 1)[0]
        # 只留原文（每 agent 一段），无重复摘要块
        assert "▼ 各 agent 摘要" not in analyst_block
        assert "· technical" not in analyst_block
        assert "【technical】技术面偏空，MACD 死叉反弹动能存疑" in analyst_block
        assert "【fundamental】基本面优异但增速放缓" in analyst_block
        assert "【sentiment】舆情偏多" in analyst_block

    def test_consistency_summary_keeps_all_analyst_agents(self):
        """回归（2026-09-09 实测）：consistency 维度【分析师章节结论】节被默认 350
        字符截断，只剩排第一的 technical——macro/fundamental/sentiment 摘要被切掉，
        标注人看不到各层结论，无法核对一致性。agent 节是各 agent 自带总结性摘要
        （数据里就有），不应二次截短，须完整展示（与注释设计意图对齐）。"""
        analyst_reports = (
            "【technical】技术面整体偏中性略偏多：股价回调后企稳，短均线重新站上中长期均线，"
            "下跌动能基本衰竭，但中期动能尚未重启，属于方向选择期。\n"
            "论据: MA5 为 1310.34(1310.338); MA10 为 1304.33(1304.327); "
            + "MACD histogram 为 -0.1254(-0.12542657925585488); "
            * 25
            + "\n【macro】宏观数据缺失，无法给出有效结论\n"
            "【fundamental】偏谨慎中性：茅台赚钱能力仍是 A 股顶级，但 2025 年营收和净利润"
            "首次明显下滑、经营现金流占净利润比例降到 0.75。\n"
            "论据: 2025年毛利率91.18%(91.18); 2025年ROE为32.53%(32.53); "
            + "2025年归母净利润同比下滑4.53%(-4.53); "
            * 20
            + "\n【sentiment】偏多但需谨慎：公司年内第六次上调自营店飞天价格至 1766 元，"
            "主力资金连续流入白酒板块，短期舆情面偏正面。"
        )
        rendered = _render(
            "consistency",
            {
                "analyst_reports": analyst_reports,
                "research_manager_decision": "RM 多空对峙",
                "risk_judgment": "watch",
                "fund_manager_decision": "approve",
                "report_conclusion": "维持 watch",
            },
        )
        s = build_summary(rendered, "consistency")
        # 4 个 agent 全部保留（不被 350 上限砍掉尾部；【sentiment】在尾部）
        assert "【technical】技术面整体偏中性略偏多" in s
        assert "【macro】宏观数据缺失" in s
        assert "【fundamental】偏谨慎中性" in s
        assert "【sentiment】偏多但需谨慎" in s
        # 无重复摘要块
        assert "▼ 各 agent 摘要" not in s
        assert "· technical" not in s

    def test_report_relevance_full_report_presented(self):
        """回归（2026-09-10 实测 acb17607）：report_relevance 的【分析报告】被默认
        350 截断——材料在表格中间腰斩（「机器人叙…」），judge 看到的完整报告含
        「一句话总结」结论，标注人只见一半（1 vs 5 假分歧）。展示层统一 5000，
        材料完整呈现 judge 所见。"""
        report = (
            "# 比亚迪 vs 特斯拉：核心对比\n 基于最新财报数据，"
            + "对比论证内容。" * 80
            + "\n**一句话总结**：比亚迪赢在'便宜且实'，特斯拉赢在'故事大'。"
        )
        rendered = _render(
            "report_relevance", {"query": "比亚迪和特斯拉哪个更值得买", "report": report}
        )
        s = build_summary(rendered, "report_relevance")
        assert "**一句话总结**：比亚迪赢在'便宜且实'" in s  # 尾部结论不被砍

    def test_consistency_summary_keeps_full_rm_section(self):
        """回归（2026-09-10 实测 81a133c2）：consistency 非 agent 节（RM 结论）被
        默认 350 截断——RM 综合判断「结论：看空（短期）」被砍。judge 的 RM 变量在
        4096 字节内是完整的，材料截断让标注人手里的信息比 judge 还少，会系统性
        污染校准。consistency 全节都是核心对比材料，按维度放大截断上限
        （与 debate_quality 同模式）。"""
        rm = (
            "研究经理总结：多空辩论裁决。多方论据…空方论据…"
            + "中间论证内容。" * 60
            + "**结论：看空（短期）。** 当前时点风险收益比不利，在此之前维持看空，不建议左侧抄底。"
        )
        rendered = _render(
            "consistency",
            {
                "analyst_reports": "【technical】偏空",
                "research_manager_decision": rm,
                "risk_judgment": "hold",
                "fund_manager_decision": "approve",
                "report_conclusion": "审批通过",
            },
        )
        s = build_summary(rendered, "consistency")
        # RM 综合判断完整保留（350 截断会把尾部结论砍掉）
        assert "**结论：看空（短期）。** 当前时点风险收益比不利" in s
        assert "不建议左侧抄底" in s


class TestHumanizeJsonBlocks:
    """标注材料人读渲染（delta 3.7）：judge 变量中的转义 JSON（交易决策/风控裁决）
    对人类不可读（""action"": ""watch"" 双重转义 + evidence_refs 埋在 JSON 里）——
    渲染层解析为人读格式，信息内容不变（同口径保持），解析失败保持原文。"""

    def test_escaped_decision_json_rendered_human_readable(self):
        raw = (
            '{"action": "watch", "confidence": 0.6, "position_size": "light", '
            '"reasoning": "维持观望", "evidence_refs": ['
            '{"claim": "均线多头", "source": "technical"}, '
            '{"claim": "回购支撑", "source": "sentiment"}]}'
        ).replace('"', '""')
        out = humanize_json_blocks("【交易决策】" + raw)
        assert "【交易决策】" in out
        assert "action: watch" in out
        assert "置信度: 0.60" in out
        assert "论据引用 2 条" in out and "technical×1" in out and "sentiment×1" in out
        assert "维持观望" in out
        assert '""' not in out  # 双重转义引号消除

    def test_plain_text_untouched(self):
        text = "approve 理由: 风控指标整体可控，批准执行。"
        assert humanize_json_blocks(text) == text

    def test_unparseable_json_kept_as_is(self):
        raw = "{broken json 不完整"
        assert humanize_json_blocks(raw) == raw


class TestCsvRoundtrip:
    def test_to_csv_header_first_line(self):
        out = to_csv([])
        assert out.splitlines()[0].split(",") == CSV_HEADER

    def test_to_csv_and_load_back_handles_bom(self, tmp_path):
        # export 脚本以 utf-8-sig（BOM）写 CSV，Excel 打开不乱码；
        # load_labeled_csv 须容忍/剥离 BOM（utf-8-sig 读无 BOM 文件同样兼容）
        rows = [
            {
                "trace_id": "t1",
                "dimension": "consistency",
                "judge_score": 4.0,
                "judge_reason": "各层一致",
                "material_summary": "…",
                "trace_url": "http://x",
            },
            {
                "trace_id": "t1",
                "dimension": "debate_quality",
                "judge_score": 5.0,
                "judge_reason": "交锋充分",
                "material_summary": "…",
                "trace_url": "http://x",
            },
        ]
        p = tmp_path / "sample.csv"
        p.write_text(to_csv(rows), encoding="utf-8-sig")
        loaded = load_labeled_csv(p)
        assert len(loaded) == 2
        assert loaded[0].trace_id == "t1"
        assert loaded[0].dimension == "consistency"
        assert loaded[0].judge_score == 4.0
        assert loaded[1].human_score is None

    def test_load_labeled_csv_parses_human_score_and_skips_unlabeled(self, tmp_path):
        rows = [
            {
                "trace_id": "t1",
                "dimension": "consistency",
                "judge_score": 4.0,
                "judge_reason": "…",
                "material_summary": "",
                "trace_url": "",
                "human_score": "3",
                "confidence": "high",
            },
            {
                "trace_id": "t2",
                "dimension": "report_relevance",
                "judge_score": 2.0,
                "judge_reason": "…",
                "material_summary": "",
                "trace_url": "",
            },
        ]
        p = tmp_path / "s.csv"
        p.write_text(to_csv(rows), encoding="utf-8")
        loaded = load_labeled_csv(p)
        assert loaded[0].human_score == 3.0
        assert loaded[1].human_score is None


class TestXlsx:
    def test_to_xlsx_freezes_header_and_wraps_summary(self, tmp_path):
        rows = [
            {
                "trace_id": "t1",
                "dimension": "debate_quality",
                "judge_score": 5.0,
                "judge_reason": "交锋充分",
                "material_summary": "长材料…" * 100,
                "trace_url": "http://x/t1",
            }
        ]
        p = tmp_path / "s.xlsx"
        to_xlsx(rows, p)
        wb = __import__("openpyxl").load_workbook(p)
        ws = wb.active
        assert ws.title == "标注表"
        assert ws.freeze_panes == "A2"  # 冻结表头，滚动打分不丢列
        col = CSV_HEADER.index("material_summary") + 1
        cell = ws.cell(row=2, column=col)
        assert cell.alignment.wrap_text is True  # 长材料自动换行，不用手动拉格子
        assert cell.alignment.vertical == "top"

    def test_load_labeled_xlsx_roundtrip(self, tmp_path):
        rows = [
            {
                "trace_id": "t1",
                "dimension": "consistency",
                "judge_score": 4.0,
                "judge_reason": "…",
                "material_summary": "…",
                "trace_url": "",
                "human_score": "3",
                "confidence": "high",
            },
            {
                "trace_id": "t2",
                "dimension": "report_relevance",
                "judge_score": 2.0,
                "judge_reason": "…",
                "material_summary": "",
                "trace_url": "",
            },
        ]
        p = tmp_path / "s.xlsx"
        to_xlsx(rows, p)
        loaded = load_labeled_xlsx(p)
        assert len(loaded) == 2
        assert loaded[0].human_score == 3.0
        assert loaded[1].human_score is None
        assert loaded[0].dimension == "consistency"


class TestHumanizeEvidenceRefsListed:
    """r2 三道关复盘：人读化把 evidence_refs 压成「论据引用 N 条（来源分布）」，标注人
    看不到任何 claim，而 judge 所见 JSON 每条 claim 都在——decision_grounding 的核心动作
    是逐条核对 claim，人与 judge 材料在此维度不等价。每条引用须以「[source] claim」列出。"""

    def test_each_evidence_ref_rendered(self):
        from evals.judge_calibration.material import humanize_json_blocks

        text = (
            "【交易决策】\n"
            '{"action": "sell", "confidence": 0.55, "reasoning": "偏空", '
            '"evidence_refs": [{"claim": "ROE 仅 3.4%", "source": "fundamental"}, '
            '{"claim": "MACD 零轴下死叉", "source": "technical"}, '
            '{"claim": "隐含PE约25倍", "source": "risk_neutral"}]}'
        )
        out = humanize_json_blocks(text)
        assert "论据引用 3 条" in out
        assert "[fundamental] ROE 仅 3.4%" in out
        assert "[technical] MACD 零轴下死叉" in out
        assert "[risk_neutral] 隐含PE约25倍" in out
        assert '{"action"' not in out


class TestTailAnchorAndAllBlocks:
    def test_scoring_instructions_do_not_leak_into_last_section(self):
        """r2 三道关复盘：consistency rubric v2 的「先明确决策语义(评分前必读)」段紧跟
        {{report_conclusion}}，末节没有尾部锚点时整段评测指令被拼进标注材料。"""
        from evals.judge_calibration.material import build_summary

        rendered = _render(
            "consistency",
            {
                "analyst_reports": "【technical】偏多",
                "research_manager_decision": "评级: 中性（置信度 0.55）",
                "risk_judgment": '{"action": "watch", "confidence": 0.5, "reasoning": "r"}',
                "fund_manager_decision": "approve",
                "report_conclusion": "综合判断观望。",
            },
        )
        s = build_summary(rendered, "consistency")
        assert "综合判断观望" in s
        assert "评分前必读" not in s
        assert "先明确决策语义" not in s

    def test_multiple_json_blocks_all_humanized(self):
        from evals.judge_calibration.material import humanize_json_blocks

        text = (
            "【交易方案】\n"
            '{"action": "buy", "confidence": 0.7, "reasoning": "a"}\n'
            "【风控裁决】\n"
            '{"action": "watch", "confidence": 0.5, "reasoning": "b"}'
        )
        out = humanize_json_blocks(text)
        assert '{"action"' not in out
        assert "action: buy" in out and "action: watch" in out
