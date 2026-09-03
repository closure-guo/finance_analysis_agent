class TestMarkdownFieldMissingFallback:
    """#109 重新定性：glm-5.3 漏输 schema 尾字段 markdown——不再整体降级为
    原始文本，而是用 summary/key_findings 合成 markdown（claims 保留）。"""

    def test_json_without_markdown_synthesizes_and_keeps_claims(self):
        from finance_agent.nodes.analysts import _parse_analyst_report

        resp = (
            '```json\n{"agent_name": "fundamental", "summary": "ROE 43.84% 高盈利", '
            '"key_findings": ["ROE 五年攀升", "现金流红灯"], '
            '"claims": [{"claim_type": "numerical", "source_type": "data", '
            '"field_ref": "profitability_metrics.ROE.2025", "stated_value": 43.84, '
            '"interpretation": "ROE 43.84%"}]}\n```'
        )
        rep = _parse_analyst_report(resp, "fundamental")
        assert rep.claims and rep.claims[0].stated_value == 43.84  # claims 保留
        assert "ROE 43.84% 高盈利" in rep.markdown  # 由 summary 合成
        assert "ROE 五年攀升" in rep.markdown  # key_findings 进 markdown
        assert rep.parse_degraded is False  # 不再整体降级

    def test_full_json_still_parses_normally(self):
        from finance_agent.nodes.analysts import _parse_analyst_report

        resp = (
            '```json\n{"agent_name": "technical", "summary": "中期下行", '
            '"key_findings": ["均线空头"], "claims": [], '
            '"markdown": "## 技术面\\n均线空头排列"}\n```'
        )
        rep = _parse_analyst_report(resp, "technical")
        assert rep.markdown == "## 技术面\n均线空头排列"
        assert rep.parse_degraded is False
