"""结算报告（issue #250）：§1.9-v2 预登记口径的消费端。

IC/ICIR 与蒙特卡洛零模型的真读数在此拼装为对外结算报告：
collect（读库取结算日主行）→ build_report_data（纯函数组装读数，红线先判）
→ render_marketing_report（markdown 渲染）。本模块只读，不写库。

红线（§1.9-v2）：可判定日主样本 < 10 → 零模型 SHALL NOT 产出（首批 T+20 结算
样本可能 <10，这是最常见路径而非异常，报告必须优雅降级）；「跑赢/跑输」类结论
必须附分位读数，单独出现的点估计 = 口径违规。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finance_agent.outcome.track_record.model import list_predictions


def collect_settled_day_masters(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """读取已结算日主行（§1.9-v2 样本口径）。

    list_predictions 全量读取（上限 100_000，见 model.list_predictions P1 注记）
    后防御性过滤：resolution_rule 为空（未结算 open 行）或 'duplicate_of_day'
    （同日重复关闭行）不进报告——结算行本应只含日主，防御照做。返回行不做状态级
    过滤（unresolvable/avoidance 等由下游按读数可用性处理）。
    """
    rows = list_predictions(limit=100_000, db_path=db_path)
    return [r for r in rows if r.get("resolution_rule") not in (None, "", "duplicate_of_day")]
