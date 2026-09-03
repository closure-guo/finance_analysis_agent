"""消融编排测试：变体输入对齐（同一快照）、聚合与结论措辞。全部 mock 节点，不调 LLM。"""

from evals.ablation import aggregate_results, build_variant_graph, conclusion_for_layer


class TestVariantGraph:
    def test_three_variants_buildable(self):
        for variant in ("analysts", "plus_debate", "full"):
            graph = build_variant_graph(variant)
            assert graph is not None

    def test_unknown_variant_raises(self):
        import pytest

        with pytest.raises(ValueError):
            build_variant_graph("nope")


class TestAggregate:
    def _runs(self, variant: str, citation: list[bool], judge: list[float]) -> list[dict]:
        return [
            {
                "variant": variant,
                "ticker": f"t{i % 3}",
                "citation_pass": c,
                "judge": {"report_relevance": j},
            }
            for i, (c, j) in enumerate(zip(citation, judge, strict=True))
        ]

    def test_layer_increment_with_ci_support(self):
        runs = (
            self._runs("analysts", [False] * 6, [2.0] * 6)
            + self._runs("plus_debate", [True] * 6, [4.0] * 6)
            + self._runs("full", [True] * 6, [4.5] * 6)
        )
        report = aggregate_results(runs)
        debate = report["layers"]["debate"]
        assert debate["judge_report_relevance"]["conclusion"] == "显著改进"
        full = report["layers"]["full"]
        assert full["judge_report_relevance"]["ci"][0] > 0

    def test_layer_without_support_flagged(self):
        runs = self._runs("analysts", [True, False], [3.0, 3.1]) + self._runs(
            "plus_debate", [True, False], [3.05, 3.0]
        )
        report = aggregate_results(runs)
        assert (
            report["layers"]["debate"]["judge_report_relevance"]["conclusion"]
            == "该层价值未获统计支持"
        )

    def test_citation_pass_rate_increment_with_ci(self):
        """citation_pass 率层增量须带配对 bootstrap CI（spec：消融以带 CI 的 pass 率衡量）。"""
        runs = (
            self._runs("analysts", [False] * 6, [2.0] * 6)
            + self._runs("plus_debate", [True] * 6, [4.0] * 6)
            + self._runs("full", [True] * 6, [4.5] * 6)
        )
        report = aggregate_results(runs)
        rate = report["layers"]["debate"]["citation_pass_rate"]
        assert rate["prev"] == 0.0
        assert rate["current"] == 1.0
        assert rate["ci"][0] > 0
        assert rate["conclusion"] == "显著改进"

    def test_citation_pass_rate_without_support(self):
        """逐 ticker pass 率交错（t0 降、t1 升）→ CI 含 0 → 未获统计支持。"""
        runs = self._runs("analysts", [True, False], [3.0, 3.0]) + self._runs(
            "plus_debate", [False, True], [3.0, 3.0]
        )
        report = aggregate_results(runs)
        rate = report["layers"]["debate"]["citation_pass_rate"]
        assert rate["ci"][0] <= 0 <= rate["ci"][1]
        assert rate["conclusion"] == "该层价值未获统计支持"


class TestConclusionWording:
    def test_ci_contains_zero_wording(self):
        c = conclusion_for_layer((-0.01, 0.02))
        assert c == "该层价值未获统计支持"

    def test_ci_positive_wording(self):
        assert conclusion_for_layer((0.05, 0.4)) == "显著改进"

    def test_ci_negative_wording(self):
        assert conclusion_for_layer((-0.4, -0.05)) == "显著退步"


class TestJudgeDimApplicability:
    """#112：judge 维度按变体适用性过滤——plus_debate 无决策/风控层，不得评
    consistency/decision_grounding（评不存在的层产伪影）。"""

    def test_analysts_only_relevance(self):
        from evals.ablation import _applicable_dims

        assert _applicable_dims("analysts") == ("report_relevance",)

    def test_plus_debate_no_decision_dims(self):
        from evals.ablation import _applicable_dims

        assert _applicable_dims("plus_debate") == ("report_relevance", "debate_quality")

    def test_full_all_dims(self):
        from evals.ablation import _applicable_dims

        assert set(_applicable_dims("full")) == {
            "report_relevance",
            "debate_quality",
            "decision_grounding",
            "consistency",
        }
