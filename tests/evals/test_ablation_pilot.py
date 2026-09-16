"""消融驱动测试（delta judge-enumeration-cap-and-ablation-materials §2）。

零 LLM：ablation 模块与 usage meter 全部注入假件，只验驱动层契约——
① judge 材料按 `(variant, ticker, repeat)` 落盘且内容即 judge_vars；
② run 记录携带材料路径与 judge 明细（分数/纯定性条数/是否封顶/枚举是否缺失）；
③ `--tickers/--repeats` 参数化并写入产物 config；
④ 断点续跑键仍为 `(variant, ticker, repeat)`，已完成 run 不重复消费。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "tests" / "scripts" / "ablation_pilot.py"


def _load_module():
    """以模块方式加载脚本（tests/scripts 非包，走 importlib）。"""
    spec = importlib.util.spec_from_file_location("ablation_pilot_under_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pilot = _load_module()


class _FakeAblation:
    """假 ablation 模块：不跑管线、不调 LLM。"""

    JUDGE_DIMS = ["report_relevance", "debate_quality", "decision_grounding", "consistency"]
    _VARIANTS = ["analysts", "plus_debate", "full"]

    def __init__(self):
        self.verify_calls = 0
        self.run_calls: list[tuple[str, str]] = []

    # 被驱动 monkeypatch 的入口
    def verify_citations(self, state: dict) -> dict:
        self.verify_calls += 1
        return {"citation_pass": True, "citation_coverage": 0.95}

    def run_variant_once(self, variant: str, snapshot: dict, query: str) -> dict:
        self.run_calls.append((variant, query))
        return {
            "final_report": f"report-{variant}",
            "citation_pass": True,
            "judge_vars": {"debate_history": f"【bull】论点: {variant}"},
            "decision": None,
        }

    def build_snapshot(self, ticker: str) -> dict:
        return {"stock_code": ticker}

    def snapshot_digest(self, state: dict) -> str:
        return f"digest-{state['stock_code']}"

    def run_judge(self, dimension: str, variables: dict) -> dict:
        # debate 维度返回带遥测的结果（模拟 v6 封顶）
        if dimension == "debate_quality":
            return {
                "name": dimension,
                "score": 4,
                "reason": "标头含纯定性论点",
                "confidence": 0.8,
                "points": [],
                "qualitative_points": 1,
                "cap_applied": True,
                "enumeration_missing": False,
            }
        return {"name": dimension, "score": 5, "reason": "ok", "confidence": 0.9}

    def run_judge_mean(self, dimension: str, variables: dict, *, repeats: int = 3) -> dict:
        """假均值协议：debate 维度模拟 [5,4,4]（round11 实测形态）。"""
        if dimension == "debate_quality":
            return {
                "name": dimension,
                "score": 4.333 if repeats >= 3 else 4.0,
                "reason": "标头含纯定性论点",
                "confidence": 0.8,
                "points": [],
                "qualitative_points": 1,
                "cap_applied": False,
                "enumeration_missing": False,
                "scores": [5, 4, 4] if repeats >= 3 else [4],
                "score_spread": 1 if repeats >= 3 else 0,
                "judge_repeats": repeats,
                "judge_failures": 0,
            }
        return {
            "name": dimension,
            "score": 5,
            "reason": "ok",
            "confidence": 0.9,
            "scores": [5] * repeats,
            "score_spread": 0,
            "judge_repeats": repeats,
            "judge_failures": 0,
        }

    def aggregate_results(self, runs: list[dict]) -> dict:
        return {"n_runs": len(runs)}


class _FakeMeter:
    def __init__(self):
        self._usage_ledger: list[dict] = []


@pytest.fixture
def env(tmp_path):
    return SimpleNamespace(
        ablation=_FakeAblation(),
        meter=_FakeMeter(),
        resume=tmp_path / "resume.json",
        materials=tmp_path / "judge_vars",
        out=tmp_path / "out",
    )


def _run(env, **kwargs):
    return pilot.run_pilot(
        tickers=kwargs.pop("tickers", ["600519"]),
        repeats=kwargs.pop("repeats", 1),
        resume_path=env.resume,
        materials_dir=env.materials,
        out_dir=env.out,
        ablation_mod=env.ablation,
        meter=env.meter,
        prompt_versions_fn=lambda: {"debate_quality": "v6"},
        **kwargs,
    )


class TestMaterialPersistence:
    def test_materials_written_per_run(self, env):
        _run(env, tickers=["600519", "000001"], repeats=2)
        names = sorted(p.name for p in env.materials.glob("*.json"))
        assert names == sorted(
            f"{variant}-{ticker}-{i}.json"
            for variant in ["analysts", "plus_debate", "full"]
            for ticker in ["600519", "000001"]
            for i in range(2)
        ), "每个 (variant, ticker, repeat) 一条材料"

    def test_material_content_is_judge_vars(self, env):
        _run(env)
        payload = json.loads((env.materials / "full-600519-0.json").read_text(encoding="utf-8"))
        assert payload == {"debate_history": "【bull】论点: full"}

    def test_run_record_carries_materials_path(self, env):
        path = _run(env, tickers=["600519"], repeats=1)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        runs = artifact["run_costs"]
        assert len(runs) == 3  # 1 标的 × 3 变体 × 1 重复
        for row in runs:
            assert row["materials_path"].endswith(
                f"{row['variant']}-{row['ticker']}-{row['repeat']}.json"
            )
            assert (env.materials / Path(row["materials_path"]).name).exists()

    def test_judge_detail_recorded(self, env):
        path = _run(env)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        full = next(r for r in artifact["run_costs"] if r["variant"] == "full")
        detail = full["judge_detail"]["debate_quality"]
        assert detail["score"] == 4.333
        assert detail["cap_applied"] is False
        assert detail["qualitative_points"] == 1
        assert detail["enumeration_missing"] is False
        assert detail["scores"] == [5, 4, 4], "每次分数随 run 落盘（噪声可见）"
        assert detail["score_spread"] == 1
        assert detail["judge_repeats"] == pilot.JUDGE_REPEATS


class TestParameterization:
    def test_config_records_actual_tickers_and_repeats(self, env):
        path = _run(env, tickers=["600519", "300308"], repeats=2)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        assert artifact["config"]["tickers"] == ["600519", "300308"]
        assert artifact["config"]["repeats"] == 2
        assert artifact["config"]["judge_repeats"] == pilot.JUDGE_REPEATS
        assert artifact["config"]["materials_dir"].endswith("judge_vars")
        assert len(artifact["run_costs"]) == 2 * 3 * 2

    def test_resume_keys_unchanged(self, env):
        _run(env, tickers=["600519"], repeats=2)
        resume = json.loads(env.resume.read_text(encoding="utf-8"))
        keys = {tuple(k) for k in resume["done_keys"]}
        assert keys == {
            (variant, "600519", i)
            for variant in ["analysts", "plus_debate", "full"]
            for i in range(2)
        }

    def test_second_run_skips_completed(self, env):
        _run(env, tickers=["600519"], repeats=1)
        calls_after_first = len(env.ablation.run_calls)
        _run(env, tickers=["600519"], repeats=1)  # 同 resume → 全部跳过
        assert len(env.ablation.run_calls) == calls_after_first, "已完成 run 不得重复消耗"

    def test_extending_repeats_only_runs_new(self, env):
        _run(env, tickers=["600519"], repeats=1)
        calls_after_first = len(env.ablation.run_calls)
        _run(env, tickers=["600519"], repeats=2)  # 只应新增 repeat=1 的三条
        assert len(env.ablation.run_calls) == calls_after_first + 3


class TestCli:
    def test_parse_args_defaults(self):
        args = pilot.parse_args([])
        assert args.tickers == pilot.TICKERS
        assert args.repeats == pilot.REPEATS

    def test_parse_args_overrides(self):
        args = pilot.parse_args(
            ["--tickers", "600519", "000001", "--repeats", "10", "--judge-repeats", "5"]
        )
        assert args.tickers == ["600519", "000001"]
        assert args.repeats == 10
        assert args.judge_repeats == 5

    def test_judge_repeats_default_is_mean_protocol(self):
        assert pilot.JUDGE_REPEATS >= 3, "默认须为多次均值（单次调用 5/4 边界有 ±1 噪声）"
