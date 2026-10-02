"""update-decision-integrity-gates Task 1：决策文本价位交叉校验器（TDD 先行）。

四 Scenario 逐条对应 openspec/changes/update-decision-integrity-gates/specs/
price-level-tooling/spec.md（触发价幻觉/空洞触发/正常直通/非价格量纲不误报），
另含 600015 反例族、risk_judge 接入测试（mock call_llm_streaming——同
tests/nodes/test_risk.py 既有模式）与「校验异常不中断管线」观测旁路护栏。

technical_indicators 手搓形态与 calc_technical 输出严格同构（分组 dict、
与 K 线等长的 list、末值=最新值、预热段 None），并有 calc_technical 全真
端到端测试钉死形态兼容。
"""

import json
import math
from unittest.mock import patch

import pandas as pd
import pytest

from finance_agent.metrics.decision_price_check import check_decision_prices
from finance_agent.metrics.levels import calc_price_levels
from finance_agent.metrics.technical import calc_technical
from finance_agent.models import TradeDecision
from finance_agent.nodes.risk import risk_judge


def _indicators(
    ma5: float | None = None,
    ma10: float | None = None,
    ma20: float | None = None,
    ma60: float | None = None,
    boll_upper: float | None = None,
    boll_middle: float | None = None,
    boll_lower: float | None = None,
) -> dict:
    """按 calc_technical 输出形态构造 technical_indicators（末值=给定值，预热段 None）。"""

    def seq(v: float | None) -> list[float | None]:
        return [None, None, v]

    return {
        "MA": {"5": seq(ma5), "10": seq(ma10), "20": seq(ma20), "60": seq(ma60)},
        "BOLL": {
            "upper": seq(boll_upper),
            "middle": seq(boll_middle),
            "lower": seq(boll_lower),
        },
    }


def _decision(**fields: object) -> TradeDecision:
    base: dict = {"action": "watch", "confidence": 0.5, "reasoning": "观望"}
    base.update(fields)
    return TradeDecision.model_validate(base)


# ── 600845 形态夹具：MA60=18.066，现价 18.10，18.8 落在全部参考带外 ──
TI_600845 = _indicators(
    ma5=18.12,
    ma10=18.09,
    ma20=18.05,
    ma60=18.066,
    boll_upper=18.60,
    boll_middle=18.05,
    boll_lower=17.95,
)
PL_600845 = {
    "available": True,
    "entry_ref": 18.10,
    "recent_high": 18.55,
    "recent_low": 17.95,
    "atr": 0.10,
    "stop_band_long": {"low": 17.90, "high": 18.00},
    "target_band_long": {"low": 18.30, "high": 18.50},
    "full_band": [17.75, 18.65],
}
CLOSE_600845 = 18.10

# ── 601066 形态夹具：现价 23.03，止损参考带上沿 22.61 ──
TI_601066 = _indicators(
    ma5=22.90,
    ma10=22.85,
    ma20=22.70,
    ma60=22.10,
    boll_upper=23.10,
    boll_middle=22.50,
    boll_lower=21.90,
)
PL_601066 = {
    "available": True,
    "entry_ref": 23.03,
    "recent_high": 23.50,
    "recent_low": 22.40,
    "atr": 0.35,
    "stop_band_long": {"low": 22.33, "high": 22.61},
    "target_band_long": {"low": 23.73, "high": 24.43},
    "full_band": [21.70, 24.20],
}
CLOSE_601066 = 23.03


class TestScenarioDeviation:
    """Scenario 1：触发价幻觉检测（偏差形态）——放量突破 MA60 并站稳 18.8。"""

    def test_hallucinated_ma60_price_registered(self):
        decision = _decision(
            inaction_reason="均线趋势未确认",
            reasoning="技术面等待信号确认，暂不行动",
            reeval_triggers=["放量突破 MA60 并站稳 18.8 以上"],
        )
        anomalies = check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["kind"] == "deviation"
        # 触发原文完整保留（Task 3 渲染按同源文本匹配）
        assert a["source_text"] == "放量突破 MA60 并站稳 18.8 以上"
        # 指标名 + 已验证值 + 偏差幅度三要素齐备
        assert a["indicator"] == "MA60"
        assert a["verified_value"] == pytest.approx(18.066)
        assert a["deviation_pct"] == pytest.approx(4.06, abs=0.01)
        assert "MA60" in a["message"]
        assert "18.066" in a["message"]
        assert "4.06" in a["message"]

    def test_decision_object_not_mutated(self):
        """纯观测：校验不得改动决策对象（放行语义的前置）。"""
        decision = _decision(reeval_triggers=["放量突破 MA60 并站稳 18.8 以上"])
        before = decision.model_dump()
        check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845)
        assert decision.model_dump() == before


class TestScenarioEmptyTrigger:
    """Scenario 2：空洞触发条件检测——站上 22.61 而现价 23.03，条件已满足。"""

    def test_breakout_below_close_registered(self):
        decision = _decision(
            inaction_reason="触发条件尚未满足",
            reeval_triggers=["价格放量站上止损参考带上沿 22.61"],
        )
        anomalies = check_decision_prices(decision, TI_601066, PL_601066, CLOSE_601066)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["kind"] == "empty_trigger"
        assert a["source_text"] == "价格放量站上止损参考带上沿 22.61"
        # 上破触发价 22.61 不高于现价 23.03：现价即验证值
        assert a["verified_value"] == pytest.approx(23.03)
        assert a["deviation_pct"] is None
        assert "22.61" in a["message"]
        assert "23.03" in a["message"]
        assert "已满足" in a["message"]

    def test_breakdown_above_close_registered(self):
        """下破对称形态：失守 23.5 而现价 23.03——下破价不低于现价，条件已满足。"""
        decision = _decision(reeval_triggers=["放量失守 MA5 23.5 则观望"])
        anomalies = check_decision_prices(decision, TI_601066, PL_601066, CLOSE_601066)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["kind"] == "empty_trigger"
        assert a["verified_value"] == pytest.approx(23.03)


class TestScenarioNormalPassThrough:
    """Scenario 3：正常触发价直通——偏差在阈值内且方向语义有效，零 anomaly。"""

    def test_valid_triggers_pass(self):
        decision = _decision(
            reeval_triggers=[
                "跌破近期低点 22.94 加速离场",
                "放量突破 24.60 后回踩不破可加仓",
            ]
        )
        ti = _indicators(
            ma5=23.10,
            ma10=23.00,
            ma20=22.85,
            ma60=22.40,
            boll_upper=23.60,
            boll_middle=22.90,
            boll_lower=22.20,
        )
        pl = {
            "available": True,
            "entry_ref": 23.03,
            "recent_high": 24.50,
            "recent_low": 22.94,
            "atr": 0.30,
            "stop_band_long": {"low": 22.43, "high": 22.73},
            "target_band_long": {"low": 23.63, "high": 24.23},
            "full_band": [22.34, 25.10],
        }
        assert check_decision_prices(decision, ti, pl, 23.03) == []

    def test_statement_of_fact_not_empty_trigger(self):
        """「已站上」是事实陈述而非再评估门槛——空洞形态不得误报（已前缀守卫）。"""
        decision = _decision(inaction_reason="股价已站上 MA20 18.9 之上，暂不追高")
        ti = _indicators(ma5=18.50, ma20=18.30, ma60=18.00)
        pl = {
            "available": True,
            "entry_ref": 19.00,
            "recent_high": 19.20,
            "recent_low": 17.90,
            "atr": 0.20,
            "stop_band_long": {"low": 18.60, "high": 18.80},
            "target_band_long": {"low": 19.40, "high": 19.80},
            "full_band": [17.50, 18.80],
        }
        anomalies = check_decision_prices(decision, ti, pl, 19.00)
        # 18.9 vs MA20 18.30 偏差 3.28% 且在参考带外 → 只登记偏差形态；
        # 「已站上」不构成空洞触发
        assert len(anomalies) == 1
        assert anomalies[0]["kind"] == "deviation"
        assert anomalies[0]["indicator"] == "MA20"
        assert "已站上" in anomalies[0]["source_text"]


class TestScenarioNonPriceDimensions:
    """Scenario 4 + 600015 反例：百分比/比值/非价格量纲 MUST NOT 误报。"""

    def test_percent_ratio_and_macro_numbers_pass(self):
        decision = _decision(
            reasoning="综合置信度 0.6；估值处于近三年 30% 分位",
            inaction_reason="赔率不足 1.2:1，单季净利降幅收敛至 18.35% 以下前观望",
            reeval_triggers=[
                "单季净利降幅收敛至 18.35% 以下",
                "赔率修复至 1:1 以上",
                "RSI 回落至 40 以下再介入",
                "成交量放大至 2.5 万手以上",
            ],
        )
        assert check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845) == []

    def test_indicator_name_numbers_not_extracted(self):
        """「MA60」「60日均线」中的数字是指标名成分，不得当价位提取。"""
        decision = _decision(
            reeval_triggers=["放量突破 MA60 并站稳 18.8 以上"],
            inaction_reason="股价位于 60日均线下方",
        )
        anomalies = check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845)
        # 仅 18.8 一处偏差 anomaly；60 不得被提取为价位（否则 60 vs 18.066 会误报）
        assert len(anomalies) == 1
        assert anomalies[0]["kind"] == "deviation"
        assert all(a["source_text"] != "60" for a in anomalies)

    def test_dates_not_extracted(self):
        """日期（2026-09-30 / 9月30日）不得当价位提取。"""
        decision = _decision(
            reeval_triggers=["2026-09-30 前若放量突破 MA60 并站稳 18.8 以上则转积极"],
        )
        anomalies = check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845)
        assert len(anomalies) == 1
        assert anomalies[0]["deviation_pct"] == pytest.approx(4.06, abs=0.01)


class TestFieldCoverage:
    """reeval_triggers 每条 + inaction_reason + reasoning 三字段全覆盖。"""

    def test_inaction_reason_and_reasoning_checked(self):
        decision = _decision(
            reasoning="回踩布林下轨 18.9 获支撑则转积极",
            reeval_triggers=[],
        )
        anomalies = check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845)
        # 布林下轨已验证值 17.95，18.9 偏差 5.29% 且在参考带外 → deviation
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["kind"] == "deviation"
        assert a["indicator"] == "布林下轨"
        assert a["verified_value"] == pytest.approx(17.95)
        # 非触发条目字段按局部片段摘录，保留原文可读形态
        assert "18.9" in a["source_text"]

    def test_buy_without_text_prices_yields_empty(self):
        decision = _decision(
            action="buy",
            confidence=0.6,
            reasoning="趋势向好，建议买入",
        )
        assert check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845) == []


class TestReferenceBandExemption:
    """参考带豁免：未点名价位落在支撑/压力带（含 sanity 放宽带）内不报偏差。"""

    def test_reasoning_stop_echo_inside_full_band_pass(self):
        """reasoning 复述止损/目标价（>2% 偏离均线但落 sanity 放宽带内）不得误报。"""
        decision = _decision(
            action="buy",
            confidence=0.6,
            reasoning="以 18.20 附近建仓，止损参考 17.50，目标参考 19.30；赔率约 1.4:1",
        )
        # 独立参考带夹具：17.50/19.30 均在 stop/target 带外、仅被放宽带豁免
        pl = {
            "available": True,
            "entry_ref": 18.10,
            "recent_high": 18.55,
            "recent_low": 17.60,
            "atr": 0.15,
            "stop_band_long": {"low": 17.80, "high": 18.00},
            "target_band_long": {"low": 18.40, "high": 18.80},
            "full_band": [16.90, 19.50],
        }
        anomalies = check_decision_prices(decision, TI_600845, pl, CLOSE_600845)
        assert anomalies == []

    def test_unnamed_price_outside_all_bands_flagged(self):
        decision = _decision(reeval_triggers=["回落至 16.80 全仓接回"])
        anomalies = check_decision_prices(decision, TI_600845, PL_600845, CLOSE_600845)
        # 16.80 距最近指标（MA60 18.066）7.0% 且落全部参考带外 → deviation
        assert len(anomalies) == 1
        assert anomalies[0]["kind"] == "deviation"


class TestMissingInputs:
    """latest_close 缺失只跳过空洞检测、仍做偏差；无任何已验证指标则整体跳过。"""

    def test_none_close_skips_empty_only(self):
        decision = _decision(
            reeval_triggers=["价格放量站上 17.50", "放量突破 MA60 并站稳 18.8 以上"]
        )
        anomalies = check_decision_prices(decision, TI_600845, PL_600845, None)
        assert len(anomalies) == 2
        assert all(a["kind"] == "deviation" for a in anomalies)
        assert all(a["verified_value"] is not None for a in anomalies)

    def test_no_verified_indicators_yields_empty(self):
        decision = _decision(reeval_triggers=["放量突破 MA60 并站稳 18.8 以上"])
        assert check_decision_prices(decision, {}, {}, None) == []
        assert (
            check_decision_prices(
                decision, {}, {"available": False, "reason": "insufficient_kline"}, None
            )
            == []
        )


class TestCalcTechnicalShapeCompatibility:
    """全真形态端到端：calc_technical/calc_price_levels 产出直接可用。"""

    def test_flat_kline_hallucinated_breakout(self):
        n = 80
        kline = pd.DataFrame(
            {
                "日期": pd.date_range("2026-06-01", periods=n),
                "开盘": [18.0] * n,
                "收盘": [18.0] * n,
                "最高": [18.05] * n,
                "最低": [17.95] * n,
                "成交量": [1000] * n,
            }
        )
        ti = calc_technical(kline)
        pl = calc_price_levels(kline)
        decision = _decision(reeval_triggers=["放量突破 MA60 并站稳 18.8 以上"])
        anomalies = check_decision_prices(decision, ti, pl, 18.0)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["kind"] == "deviation"
        assert a["indicator"] == "MA60"
        assert a["verified_value"] == pytest.approx(18.0)
        assert a["deviation_pct"] == pytest.approx(4.44, abs=0.01)

    def test_warmup_none_values_fall_back_to_closest(self):
        """预热段（None 末值）指标不可用：点名指标缺值回退最接近已验证值，不抛异常。"""
        ti = {
            "MA": {"5": [None] * 3, "10": [None] * 3, "20": [None] * 3, "60": [None] * 3},
            "BOLL": {"upper": [None] * 3, "middle": [None] * 3, "lower": [None] * 3},
        }
        decision = _decision(reeval_triggers=["放量突破 MA60 并站稳 18.8 以上"])
        anomalies = check_decision_prices(decision, ti, {}, 18.10)
        # MA60 预热段缺值 → 回退唯一可用已验证值（最新收盘 18.10）做偏差核对
        assert len(anomalies) == 1
        assert anomalies[0]["indicator"] == "最新收盘价"
        assert anomalies[0]["verified_value"] == pytest.approx(18.10)


class TestRiskJudgeIntegration:
    """risk_judge 接入（update-decision-price-gate 门禁化）：anomaly → 打回重试一次，
    仍异常 gate fail、残留落 state；无 anomaly 直通。"""

    @staticmethod
    def _kline_601066() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "日期": ["2026-09-29", "2026-09-30"],
                "开盘": [22.80, 22.95],
                "收盘": [22.90, 23.03],
                "最高": [23.00, 23.10],
                "最低": [22.70, 22.90],
                "成交量": [1000, 1200],
            }
        )

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_risk_judge_returns_decision_price_anomalies(self, mock_llm):
        """watch 决策含空洞触发价 → 打回一次，stub 仍同输出 → gate fail、残留落 state。"""
        mock_llm.return_value = json.dumps(
            {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "等待趋势确认",
                "inaction_reason": "触发条件尚未满足",
                "reeval_triggers": ["价格放量站上止损参考带上沿 22.61"],
            },
            ensure_ascii=False,
        )
        state = {
            "trader_plan": {},
            "risk_debate_history": [],
            "technical_indicators": TI_601066,
            "price_levels": PL_601066,
            "kline": self._kline_601066(),
        }
        result = risk_judge(state)
        assert mock_llm.call_count == 2  # anomaly 打回重试恰一次（门禁回路）
        decision = result["final_trade_decision"]
        assert decision.action == "watch"  # risk_judge 层照常产出决策（阻断在 after_risk_judge）
        gate = result["decision_price_gate"]
        assert gate["result"] == "fail"
        assert "已打回仍未通过" in gate["note"]
        anomalies = result["decision_price_anomalies"]
        assert len(anomalies) == 1
        assert anomalies[0]["kind"] == "empty_trigger"
        assert anomalies[0]["verified_value"] == pytest.approx(23.03)

    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_risk_judge_buy_without_anomalies(self, mock_llm):
        mock_llm.return_value = json.dumps(
            {
                "action": "buy",
                "confidence": 0.6,
                "reasoning": "趋势向好，建议买入",
                "entry_price": 51.05,
                "stop_loss": 49.5,
                "target_price": 54.5,
            },
            ensure_ascii=False,
        )
        state = {
            "trader_plan": {},
            "risk_debate_history": [],
            "technical_indicators": TI_601066,
            "price_levels": PL_601066,
            "kline": self._kline_601066(),
        }
        result = risk_judge(state)
        assert result["decision_price_anomalies"] == []
        assert math.isfinite(result["final_trade_decision"].entry_price)

    @patch(
        "finance_agent.nodes.risk.check_decision_prices", side_effect=RuntimeError("checker boom")
    )
    @patch("finance_agent.nodes._llm_utils.call_llm_streaming")
    def test_checker_error_does_not_interrupt_pipeline(self, mock_llm, _mock_check):
        """校验器自身异常：登记为空并放行（spec：MUST NOT 硬中断管线）。"""
        mock_llm.return_value = json.dumps(
            {
                "action": "watch",
                "confidence": 0.5,
                "reasoning": "观望",
                "inaction_reason": "多因素均衡",
                "reeval_triggers": ["价格放量站上止损参考带上沿 22.61"],
            },
            ensure_ascii=False,
        )
        result = risk_judge({"trader_plan": {}, "risk_debate_history": []})
        assert result["final_trade_decision"].action == "watch"
        assert result["decision_price_anomalies"] == []


class TestFalsePositiveFix688072:
    """fix-decision-price-check-false-positives：688072 重跑实证的两个误报回归。

    案例背景（incident 034 / trace 7f43b9c9…）：reasoning 的「VaR95单日6.6%」
    曾被误读为股价 95 vs 近期低点 570 偏差 83.33%；触发条件「回撤至610以下…
    站稳610」的回踩确认结构曾被句法命中上破模式判空洞，导致门禁误拦。
    """

    STATE = {
        "available": True,
        "entry_ref": 640.0,
        "recent_low": 570.0,
        "recent_high": 945.0,
        "stop_band_long": {"low": 570.0, "high": 605.0},
        "target_band_long": {"low": 500.0, "high": 560.0},
    }

    GEN1_TRIGGER = "价格回撤至610以下且连续5日收盘站稳610并缩量企稳（量化原610企稳条件）"
    GEN2_TRIGGER = (
        "价格有效回撤至近期低点570-605止损带区域（需实际跌破610后连续5日收盘"
        "站稳610之上且成交量萎缩，形成回踩确认的企稳结构，而非当前640价位下直接满足）"
    )
    VAR_REASONING = (
        "(1)以PEG口径论证86倍PE便宜依赖+1324%单期增速可外推，属'线性外推'；"
        "(2)VaR95单日6.6%不能证明'高波动来自上行弹性'，最大回撤30.37%是已实现极值。"
    )

    def _decision(self, trigger: str, reasoning: str) -> TradeDecision:
        return TradeDecision.model_validate(
            {
                "action": "watch",
                "confidence": 0.6,
                "reasoning": reasoning,
                "inaction_reason": trigger,
                "reeval_triggers": [trigger],
            }
        )

    def test_var95_not_misread_as_price(self):
        """缺陷 A：VaR95 语境的 95 不再被当股价报偏差。"""
        anoms = check_decision_prices(
            self._decision(" MACD柱线重新翻正且MA5收复MA10 ".strip(), self.VAR_REASONING),
            {},
            self.STATE,
            640.0,
        )
        assert not [
            a for a in anoms if "95" in str(a.get("verified_value")) or "95" in a["message"]
        ]

    def test_var_percent_and_chinese_forms_not_misread(self):
        """VaR(95% / 在险价值95 变体形态同样不误报。"""
        for reasoning in ("VaR(95%置信)下单日6.6%", "在险价值95口径下回撤可控"):
            anoms = check_decision_prices(
                self._decision("跌破近期低点570重估", reasoning), {}, self.STATE, 640.0
            )
            assert not [a for a in anoms if "95" in a["message"]], reasoning

    def test_compound_retest_trigger_gen1_not_empty(self):
        """缺陷 B：gen1 复合回踩（回撤至610…站稳610）不判空洞。"""
        anoms = check_decision_prices(
            self._decision(self.GEN1_TRIGGER, "观望等待回踩确认"), {}, self.STATE, 640.0
        )
        assert not [a for a in anoms if a["kind"] == "empty_trigger"]

    def test_compound_retest_trigger_gen2_not_empty(self):
        """缺陷 B：gen2 复合回踩（跌破610后站稳610之上）不判空洞。"""
        anoms = check_decision_prices(
            self._decision(self.GEN2_TRIGGER, "观望等待回踩确认"), {}, self.STATE, 640.0
        )
        assert not [a for a in anoms if a["kind"] == "empty_trigger"]

    def test_simple_breakout_still_empty(self):
        """护栏：单上破无下破语境（spec 场景）照常判空洞——豁免不得扩大化。"""
        anoms = check_decision_prices(
            self._decision("价格放量站上止损参考带上沿605", "等待企稳"), {}, self.STATE, 640.0
        )
        assert [a for a in anoms if a["kind"] == "empty_trigger"]

    def test_real_hallucinated_price_still_reported(self):
        """护栏：真幻觉价位（无 var 语境的裸 95）照常报偏差——修复只豁免风险度量语境。"""
        anoms = check_decision_prices(
            self._decision("目标价看到 95 元附近减仓", "技术形态走弱"), {}, self.STATE, 640.0
        )
        assert [a for a in anoms if a["kind"] == "deviation" and "95" in a["message"]]
