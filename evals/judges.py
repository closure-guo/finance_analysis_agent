# evals/judges.py
"""LLM-as-Judge 评估器(spec Requirement「LLM-as-Judge 评估器与 rubric 标准」)。

- 裁判模型 deepseek/deepseek-chat,temperature=0(可复现)
- rubric 末尾强约束 JSON {score, reason} + 「不以篇幅长短论优劣」
- 解析失败重试一次,仍失败 score=None(计入失败率,不阻塞实验)
- judge generation 经独立 Langfuse(environment="langfuse-llm-as-a-judge")
  client 包裹,成本 Dashboard 独立核算;无凭据降级为无 trace 直调

singleton 说明:judge client 用模块级 `_judge_client` 单例(而非 @lru_cache)。
测试隔离:`tests/evals/test_judges.py` 的 autouse fixture
`_reset_judge_singleton` 在每个用例前后直接赋值 None 重置单例;
lru_cache 缓存的 None 会令后续「有凭据」用例拿不到 client、不再调
`_create_judge_client`,断言失败。模块变量等价于「可重置的单例」。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from finance_agent.nodes._llm_utils import parse_json_response

if TYPE_CHECKING:
    from langfuse import Langfuse


def _judge_model() -> str:
    """调用时读环境（时序 bug 防护）：``python -m evals.run`` 的模块 import
    先于 main() 的 load_dotenv 执行，import 时固化常量会拿到空值 → 跑批
    judge 全败而「先 dotenv 后 import」的单测全通（baseline-v2 28 项全败根因）。
    """
    return os.getenv("JUDGE_MODEL", "openai/deepseek-v4-flash")


def _judge_base_url() -> str:
    """裁判端点：JUDGE_BASE_URL 优先，回退主 LLM 中转（LLM_BASE_URL）。"""
    return os.getenv("JUDGE_BASE_URL") or os.getenv("LLM_BASE_URL", "") or ""


def _judge_api_key() -> str:
    """裁判凭据：JUDGE_API_KEY 优先，回退主 LLM（LLM_API_KEY）。"""
    return os.getenv("JUDGE_API_KEY") or os.getenv("LLM_API_KEY", "") or ""


JUDGE_ENV = "langfuse-llm-as-a-judge"

_JSON_TAIL = '只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}\n不以篇幅长短论优劣。'

RUBRICS: dict[str, str] = {
    "report_relevance": """你是投资研究报告评审专家。
【用户查询】{{query}}
【分析报告】{{report}}
评估报告对查询的切题度:
5 = 完全切题,紧扣查询意图展开
4 = 基本切题,少量无关内容
3 = 部分切题,有显著偏离或答非所需的段落
2 = 大部分答非所问,仅边缘相关
1 = 完全答非所问
"""
    + _JSON_TAIL,
    "debate_quality": """你是投资辩论质量评审专家。
【多空辩论记录】{{debate_history}}
评估辩论的实质交锋程度:
5 = 双方逐条回应对方论点且引用具体证据(数据/事实)
4 = 有实质交锋,证据基本充分,个别论点空泛
3 = 有交锋但多为立场声明,证据引用不足
2 = 交锋形式化,双方自说自话
1 = 单方输出或内容空洞,无实质辩论
"""
    + _JSON_TAIL,
    "decision_grounding": """你是投资决策依据评审专家。
【分析师结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【交易决策】{{trade_decision}}
评估交易决策的论据是否有前文支撑:
5 = 决策的每条论据都能在分析师结论/辩论结论中找到出处
4 = 主要论据有出处,个别细节无明确支撑
3 = 部分论据有出处,存在未论证的跳跃
2 = 论据与前文关联薄弱,或与前文结论有张力未解释
1 = 决策与前文矛盾,或论据无中生有
"""
    + _JSON_TAIL,
    "consistency": """你是投资报告一致性评审专家。
【分析师章节结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【Risk Judge 裁决】{{risk_judgment}}
【Fund Manager 最终决策】{{fund_manager_decision}}
【最终报告结论章节】{{report_conclusion}}
评估各层结论的一致性:
5 = 各层结论完全一致,无静默推翻
4 = 基本一致,个别表述差异但不影响方向
3 = 存在不一致但已显式说明理由
2 = 存在未说明的结论冲突
1 = 明显自相矛盾(如 Fund Manager 批准与 Risk Judge 否决相悖)
特别关注:Fund Manager 结论是否与 Risk Judge 裁决一致;报告结论章节是否与分析师章节一致。
"""
    + _JSON_TAIL,
}


def _create_judge_client(environment: str) -> Langfuse:
    """构造 judge 专用 Langfuse client(独立 environment,成本独立核算)。

    client 构造统一收敛到此函数,便于测试 patch 隔离。
    """
    from langfuse import Langfuse

    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        environment=environment,
    )


# 模块级单例;测试可 `@patch("evals.judges._judge_client", None)` 跨用例重置。
_judge_client: Langfuse | None = None


def get_judge_langfuse() -> Langfuse | None:
    """judge client 单例;无凭据返回 None(降级为无 trace 直调)。

    单例缓存于模块级 `_judge_client`;构造失败(Langfuse 不可用)也降级 None,
    永不抛异常阻塞 judge。
    """
    global _judge_client
    if _judge_client is not None:
        return _judge_client
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    try:
        _judge_client = _create_judge_client(JUDGE_ENV)
        return _judge_client
    except Exception:
        return None


def _call_judge_llm(prompt: str) -> str:
    """裁判调用:有凭据时经 judge client generation 包裹,否则直调。"""
    import litellm

    kwargs = {
        "model": _judge_model(),
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
        "timeout": 120,  # 防 judge 调用无限挂起（与 harness 路径一致）
    }
    if _judge_base_url():
        kwargs["api_base"] = _judge_base_url()
    if _judge_api_key():
        kwargs["api_key"] = _judge_api_key()
    client = get_judge_langfuse()
    if client is None:
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""
    with client.start_as_current_observation(
        name="judge", as_type="generation", model=_judge_model(), input=prompt
    ) as gen:
        resp = litellm.completion(**kwargs)
        text = resp.choices[0].message.content or ""
        gen.update(output=text)
        return text


def _render(dimension: str, variables: dict[str, str]) -> str:
    """rubric 模板 {{var}} 单次替换;未提供的变量替换为空串(避免 judge 看到裸占位符)。

    单次扫描(re.sub 回调)而非逐键 str.replace 循环:后者会把变量值里
    字面 {{another_key}} 二次替换掉。回调内 variables.get(...) 只对原始模板
    的每个占位符求值一次,值中出现的 {{...}} 不会被重新扫描。
    """
    return re.sub(
        r"\{\{(\w+)\}\}",
        lambda m: str(variables.get(m.group(1), "")) or "",
        RUBRICS[dimension],
    )


# 各维度依赖的关键输入变量（评估链路输入合同，delta 3.4）：
# 缺失/为空时该维度记 input_missing 跳过，不得对空输入出具正常分数
# （r5 校准教训：空辩论静默打 1 分混入均值，「自信但失真」）。
_DIMENSION_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "report_relevance": ("report",),
    "debate_quality": ("debate_history",),
    "decision_grounding": ("analyst_reports", "research_manager_decision"),
    "consistency": ("analyst_reports", "report_conclusion"),
}


def _input_missing(dimension: str, variables: dict[str, str]) -> str | None:
    """返回首个缺失的变量名；齐全返回 None。"""
    for var in _DIMENSION_REQUIRED_VARS.get(dimension, ()):
        if not str(variables.get(var, "")).strip():
            return var
    return None


def run_judge(dimension: str, variables: dict[str, str]) -> dict:
    """跑一个 Judge 维度;解析失败重试一次,仍失败 score=None。

    输入合同：维度关键变量缺失 → score=None + reason="input_missing"
    （不调 LLM、不评分），保证评估结果不被空输入污染。

    Returns: {"name": dimension, "score": int 1-5 | None, "reason": str}
    """
    missing = _input_missing(dimension, variables)
    if missing is not None:
        return {"name": dimension, "score": None, "reason": f"input_missing:{missing}"}
    prompt = _render(dimension, variables)
    for _attempt in range(2):
        try:
            data = parse_json_response(_call_judge_llm(prompt))
            score = int(data["score"])
            if not 1 <= score <= 5:
                raise ValueError(f"score 越界: {score}")
            return {"name": dimension, "score": score, "reason": str(data.get("reason", ""))}
        except Exception:  # noqa: S112 -- 故意静默重试;解析失败已通过最终 judge_parse_failed 记录
            continue
    return {"name": dimension, "score": None, "reason": "judge_parse_failed"}
