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


class TestConclusionWording:
    def test_ci_contains_zero_wording(self):
        c = conclusion_for_layer((-0.01, 0.02))
        assert c == "该层价值未获统计支持"

    def test_ci_positive_wording(self):
        assert conclusion_for_layer((0.05, 0.4)) == "显著改进"

    def test_ci_negative_wording(self):
        assert conclusion_for_layer((-0.4, -0.05)) == "显著退步"
