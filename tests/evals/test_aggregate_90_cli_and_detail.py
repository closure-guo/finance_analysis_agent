"""消融聚合脚本的 CLI 参数化与 judge 明细分布渲染（metrics.md §3 两处小账）。

背景（metrics.md 待办原文）：
① 脚本硬编码旧工作树路径 `.worktrees/evals-boot/reports/ablation/resume.json`
   （新驱动默认写 `reports/ablation/resume.json`）且硬编码「< 90 条即退出」
   → 参数化（--resume/--min-runs/--out-dir）；
② 脚本未读新增的 `judge_detail`（scores/score_spread/qualitative_points）
   → 90 条权威报告须附「judge 极差与纯定性条数」分布，使 debate 维度取值域
   压缩（v6 4.0–4.333）的影响可见。

渲染纯函数测试见 `test_aggregate_90_render.py`（该文件声明路径/阈值不属其范围）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from evals.ablation import aggregate_results

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "tests" / "scripts" / "ablation_aggregate_90.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ablation_aggregate_90_cli_under_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


agg90 = _load_module()


class TestCliConfig:
    """参数化：默认路径指向新驱动产物位置，阈值与输出目录可覆盖。"""

    def test_defaults_point_to_new_driver_location(self):
        cfg = agg90.resolve_config([])
        assert Path(cfg.resume) == Path("reports/ablation/resume.json"), (
            "默认 resume 必须指向新驱动产物位置（旧 .worktrees/evals-boot 路径已废弃）"
        )
        assert cfg.min_runs == 90
        assert Path(cfg.out_dir) == Path("reports/ablation")

    def test_overrides(self):
        cfg = agg90.resolve_config(["--resume", "x/y/r.json", "--min-runs", "5", "--out-dir", "o"])
        assert Path(cfg.resume) == Path("x/y/r.json")
        assert cfg.min_runs == 5
        assert Path(cfg.out_dir) == Path("o")

    def test_out_dir_defaults_to_resume_parent(self):
        cfg = agg90.resolve_config(["--resume", "a/b/r.json"])
        assert Path(cfg.out_dir) == Path("a/b")

    def test_cli_runs_standalone(self):
        """直接调用（文档用法 `uv run python tests/scripts/...`）须能 import evals。

        脚本自带 sys.path 引导（同 decision_action_distribution.py）；缺引导时
        本测试以 ModuleNotFoundError 退出码非零而红。
        """
        import subprocess

        proc = subprocess.run(  # noqa: S603 -- sys.executable 固定路径，参数为内联常量
            [sys.executable, str(_SCRIPT), "--help"], capture_output=True, text=True, timeout=120
        )
        assert proc.returncode == 0, proc.stderr
        assert "--resume" in proc.stdout and "--min-runs" in proc.stdout

    def test_missing_resume_exits_with_clear_message(self, tmp_path):
        """首跑最常见失败形态：台账不存在 → SystemExit 带路径提示，不抛原始 traceback。"""
        import pytest

        with pytest.raises(SystemExit) as ei:
            agg90.main(["--resume", str(tmp_path / "nope.json")])
        assert "台账不存在" in str(ei.value)

    def test_min_runs_gate_blocks_incomplete_batch(self, tmp_path):
        """阈值可配置：不足 min-runs 时退出（原硬编码 90 的泛化）。"""
        import json

        import pytest

        resume = tmp_path / "resume.json"
        resume.write_text(
            json.dumps({"runs": [{"variant": "analysts", "ticker": "600519"}]}), "utf-8"
        )
        with pytest.raises(SystemExit) as ei:
            agg90.main(["--resume", str(resume), "--min-runs", "2"])
        assert "≥2 条" in str(ei.value)


def _run(variant: str, ticker: str, judge_score: float, detail: dict | None) -> dict:
    row = {
        "variant": variant,
        "ticker": ticker,
        "citation_pass": True,
        "judge": {"report_relevance": judge_score},
        "llm_calls": 10,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "citation_coverage": 0.9,
    }
    if detail is not None:
        row["judge_detail"] = detail
    return row


class TestJudgeDetailSection:
    """judge 明细分布：极差（score_spread）与纯定性条数（qualitative_points）。"""

    def test_section_lists_spread_and_qualitative_stats(self):
        runs = [
            _run(
                "analysts",
                "600519",
                4.0,
                {"report_relevance": {"score": 4.0, "score_spread": 0.0, "qualitative_points": 2}},
            ),
            _run(
                "analysts",
                "000001",
                5.0,
                {"report_relevance": {"score": 5.0, "score_spread": 1.0, "qualitative_points": 4}},
            ),
            _run(
                "plus_debate",
                "600519",
                4.333,
                {
                    "debate_quality": {
                        "score": 4.333,
                        "score_spread": 0.333,
                        "qualitative_points": 1,
                    }
                },
            ),
            _run(
                "plus_debate",
                "000001",
                4.0,
                {"debate_quality": {"score": 4.0, "score_spread": 0.0, "qualitative_points": 0}},
            ),
        ]
        text = "\n".join(agg90.render_report(aggregate_results(runs), runs))
        assert "judge 明细分布" in text
        assert "score_spread" in text
        assert "纯定性条数" in text
        # 极差中位/最大：analysts report_relevance (0.0, 1.0) → 0.5 / 1
        assert "0.5 / 1" in text
        # 纯定性条数：analysts (2,4) → 3 / 4
        assert "3 / 4" in text
        # plus_debate debate_quality 出现（取值域压缩可见）
        assert "debate_quality" in text

    def test_missing_detail_not_fabricated(self):
        """旧记录无 judge_detail → 不伪造数字，渲染显式说明行。"""
        runs = [_run("analysts", "600519", 4.0, None), _run("full", "000001", 4.0, None)]
        text = "\n".join(agg90.render_report(aggregate_results(runs), runs))
        assert "judge 明细分布" in text
        assert "无可读明细" in text, "无明细须显式说明，不得静默消失也不得伪造 0"

    def test_enumeration_missing_count_rendered_when_present(self):
        runs = [
            _run(
                "analysts",
                "600519",
                4.0,
                {
                    "report_relevance": {
                        "score": 4.0,
                        "score_spread": 0.0,
                        "qualitative_points": 1,
                        "enumeration_missing": True,
                    }
                },
            ),
            _run(
                "analysts",
                "000001",
                4.0,
                {
                    "report_relevance": {
                        "score": 4.0,
                        "score_spread": 0.0,
                        "qualitative_points": 1,
                        "enumeration_missing": False,
                    }
                },
            ),
        ]
        text = "\n".join(agg90.render_report(aggregate_results(runs), runs))
        assert "枚举缺失" in text  # 1/2 计数可见
