"""运维 API 端点族(delta add-eval-ops-console Task 3):``/api/v1/ops/*``。

承载「日批状态 / 手动补跑 / cohort 开关与时刻 / 回测与探针 / 健康检查 / 报告注册表」
六个面,前端设置中心「评估运维」分区按本文件契约实现(字段名逐字对齐实施计划 §Task 3)。

设计要点
--------
- **状态**：五任务排程 / 下次触发 / 最近运行 / 历史。``scheduler_running`` 以「句柄是真实
  ``BackgroundScheduler`` 且 ``running``」判定,不只看非 None——其它测试模块会把
  ``scheduler._scheduler`` 泄漏成 Mock,不得据此冒充「已运行」;未运行(TESTING=1 或
  显式禁用)如实返回 ``false``(200),不以 500 或空列表冒充正常。
- **cohort 行与 cohort 块同源**：``SCHEDULES["cohort_batch"]`` 只是调度器启动期刷新的
  快照(TESTING 下永不刷新),状态接口按 ``get_cohort_settings()`` 渲染该行,二者不可能矛盾。
- **悬挂 running 行清扫**：进程死亡遗留的 ``running`` 行在状态接口读到时就地收尾为
  ``failed``(reason ``stale_process_restart``);判定依据是「行开始时刻早于本进程启动
  时刻」——本进程启动的任务行不可能满足,故不会误杀正在跑的补跑/长任务。
- **运行历史取最新行**：定时失败每次尝试各留一行(重试语义),``last_run`` 只取最新行,
  ``history`` 保留最近 ``HISTORY_LIMIT`` 行供「重试了几次」可查。
- **手动补跑**：``run_job`` 在 ``asyncio.to_thread`` 中执行(不阻塞事件循环)。任务失败
  返回 dict(``status="failed"``)而非抛异常,端点必须把它翻成 **500**(非 2xx),
  失败原因同时经响应 ``detail`` 与运行历史双通道可见,不得伪装成 202 成功。
  只有三类是异常:``ValueError``(未知 job → 404)、``JobAlreadyRunning`` /
  ``CohortDisabled``(→ 409)。
- **长任务(回测/探针/健康检查)**：同类单飞锁 + 后台线程执行,端点立即 202 返回
  ``run_id``;结果落 ``job_runs``(job_id = backtest/probe/health),经
  ``GET /runs/{run_id}`` 读取。summary 只放裁剪版(逐题 details / 逐标的一致率明细
  不进 summary),完整报告在 md/json。
- **formal 批门禁在任何回放之前**：预登记(本文件直接调 ``assert_preregistered``)
  → 抽样 → 干净窗口(``batches.prepare_backtest``),不过 → 409 + 原因,任务不派发;
  门禁通过的结果随任务透传(不重复取数)。``CleanWindowError`` 为 Task 4 层异常,
  运行期解析(见 ``_is_clean_window_refusal``),避免本模块导入期耦合 batch 层。

红线：烧钱语义(预算熔断 / 串行 / usage 真值记账)一行不改——本模块只做查看与触发,
全部安全语义沿用既有实现;cohort 开关关闭时手动跑批拒绝且零 LLM 调用。
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from apscheduler.schedulers.background import BackgroundScheduler
from evals.causal_ablation.preregister import (
    OUTCOME_REQUIRED_FIELDS,
    MissingPreregistrationError,
    assert_preregistered,
)
from evals.causal_ablation.status_index import collect_status_index
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from finance_agent.outcome.cohort.model import init_cohort_runs, list_cohort_runs
from finance_agent.outcome.cohort.runner import _resolve_budget as _cohort_budget
from finance_agent.outcome.ops.jobs import (
    JOB_IDS,
    JOB_LABELS,
    SCHEDULES,
    CohortDisabled,
    JobAlreadyRunning,
    run_job,
)
from finance_agent.outcome.ops.model import (
    COHORT_ENABLED_KEY,
    COHORT_HOUR_KEY,
    COHORT_MINUTE_KEY,
    finish_job_run,
    get_cohort_settings,
    insert_job_run,
    last_job_run,
    list_job_runs,
    set_config,
)
from finance_agent.outcome.scheduler import get_scheduler, reschedule_cohort

logger = logging.getLogger("finance_agent.ops_api")

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])

# 每任务返回的最近运行条数(定时失败每次尝试各一行,故不只取 1 行——重试次数可查)
HISTORY_LIMIT = 10

# 回测报告注册表目录(相对仓库根;测试可 patch)
BACKTEST_RESULTS_DIR = Path("evals/backtest/results")
# 正式批预登记门禁目录 + 本实验文档过滤(与 evals.backtest.run_backtest 同源约定)
PREREGISTER_DIR = Path("evals/ablation/preregister")
PREREGISTER_NAME_CONTAINS = "outcome"

# 报告定位标签:复用 evals 的 pathway/skill 词表 + 泄漏降级态(「上界证据」)
POSITIONING_PATHWAY = "pathway"
POSITIONING_SKILL = "skill"
POSITIONING_UPPER_BOUND = "upper_bound"

# 长任务:kind → (batch 层函数名, summary 裁剪器)
_TASK_FUNC_NAMES: dict[str, str] = {
    "backtest": "run_backtest_task",
    "probe": "run_probe_task",
    "health": "run_health_task",
}
# 同类长任务单飞锁(进程内;单 uvicorn worker 前提)
_KIND_LOCKS: dict[str, threading.Lock] = {kind: threading.Lock() for kind in _TASK_FUNC_NAMES}

# 本进程启动时刻:早于它的 running 行必为上一进程遗留(悬挂行清扫依据)
_PROCESS_STARTED_AT = datetime.now().isoformat()

_HIT_RATE_RE = re.compile(r"direction_hit_rate[：:]\s*([0-9]+(?:\.[0-9]+)?)\s*%")
_ROOT_KEYS = ("enabled", "hour", "minute")


# ── 请求模型 ──


class CohortUpdate(BaseModel):
    """cohort 开关/时刻局部更新(字段缺省 = 不改该项);越界由 pydantic 翻 422。"""

    enabled: bool | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)


class BacktestRequest(BaseModel):
    batch_kind: str = "pathway"
    codes: list[str]
    per_regime: int = Field(default=10, ge=1, le=50)
    repeats: int = Field(default=3, ge=1, le=10)
    as_of: str | None = None


class ProbeRequest(BaseModel):
    codes: list[str]
    decision_date: str = Field(min_length=1)
    window_days: int = Field(default=20, ge=1, le=250)
    n_tickers: int = Field(default=10, ge=1, le=100)
    seed: int = 42


# ── 批次层函数解析(延迟导入:本模块导入期不拉起 evals/backtest 重依赖)──


def _resolve_batch_func(name: str) -> Callable[..., Any]:
    """按名解析 ``outcome.ops.batches`` 的进程内封装函数(Task 4)。"""
    from finance_agent.outcome.ops import batches

    return cast(Callable[..., Any], getattr(batches, name))


def _is_clean_window_refusal(exc: BaseException) -> bool:
    """是否 Task 4 的干净窗口拒绝(运行期解析该异常类型,避免导入期耦合 batch 层)。"""
    from finance_agent.outcome.ops.batches import CleanWindowError

    return isinstance(exc, CleanWindowError)


# ── 状态:五任务 + cohort ──


def _scheduler_running() -> bool:
    """调度器是否**真在运行**;未启动/句柄被换成就地 Mock → False。"""
    scheduler = get_scheduler()
    if not isinstance(scheduler, BackgroundScheduler):
        return False
    try:
        return bool(scheduler.running)
    except Exception:  # noqa: BLE001 - 状态接口不得因调度器内部异常 500
        logger.warning("读取 scheduler.running 失败,按未运行处理", exc_info=True)
        return False


def _next_fire_time(job_id: str) -> str | None:
    """该任务的下次触发时间(ISO);调度器未运行/无该任务 → None(不冒充)。"""
    scheduler = get_scheduler()
    if not isinstance(scheduler, BackgroundScheduler):
        return None
    try:
        jobs = scheduler.get_jobs()
    except Exception:  # noqa: BLE001 - 同上
        logger.warning("读取 scheduler jobs 失败,next_fire_time 按 None 处理", exc_info=True)
        return None
    for job in jobs:
        if getattr(job, "id", None) == job_id:
            next_run = getattr(job, "next_run_time", None)
            return next_run.isoformat() if next_run is not None else None
    return None


def _sweep_stale_running() -> list[int]:
    """清扫上一进程遗留的悬挂 ``running`` 行 → ``failed``(stale_process_restart)。

    只清扫「开始时刻早于本进程启动时刻」的行:本进程启动的补跑/长任务行必然更晚,
    不会被并发轮询误杀。清扫失败只记日志(状态接口不因它 500)。
    """
    swept: list[int] = []
    try:
        for row in list_job_runs(limit=1000):
            if row["status"] != "running" or str(row["started_at"]) >= _PROCESS_STARTED_AT:
                continue
            finish_job_run(
                int(row["run_id"]),
                status="failed",
                summary={"stale": True, "reason": "stale_process_restart"},
                error="stale_process_restart: 进程重启遗留的悬挂运行行,按失败收尾",
            )
            swept.append(int(row["run_id"]))
    except Exception:  # noqa: BLE001 - 清扫是自愈动作,失败不得阻断状态读取
        logger.exception("悬挂 running 行清扫失败(忽略)")
        return swept
    if swept:
        logger.warning("已清扫进程重启遗留的 running 行 %d 条: %s", len(swept), swept)
    return swept


def _today_cohort_stats() -> dict[str, int]:
    """今日 cohort 记账汇总(花费 = 已记 token 真值之和;skipped 行无 usage 不计)。"""
    day = datetime.now().strftime("%Y-%m-%d")
    try:
        init_cohort_runs()  # 幂等建表(读接口首次调用不因缺表报 no such table)
        rows = list_cohort_runs(trade_date=day)
    except Exception:  # noqa: BLE001 - 今日花费读取失败不得使状态接口 500
        logger.warning("读取今日 cohort 记账失败,按零披露", exc_info=True)
        return {"spend": 0, "success": 0, "failure": 0}
    return {
        "spend": sum(int(row["tokens_total"] or 0) for row in rows),
        "success": sum(1 for row in rows if row["status"] == "success"),
        "failure": sum(1 for row in rows if row["status"] == "failure"),
    }


def _cohort_block(settings: dict[str, Any]) -> dict[str, Any]:
    """cohort 状态块(``/jobs`` 与 ``/cohort`` 共用同一形状,前端逐字消费)。"""
    stats = _today_cohort_stats()
    return {
        "enabled": settings["enabled"],
        "hour": settings["hour"],
        "minute": settings["minute"],
        "budget_tokens": _cohort_budget(None),
        "today_spend": stats["spend"],
        "today_success": stats["success"],
        "today_failure": stats["failure"],
    }


def _job_rows(cohort: dict[str, Any]) -> list[dict[str, Any]]:
    """五任务状态行(顺序 = JOB_IDS = 调度注册顺序)。"""
    rows: list[dict[str, Any]] = []
    for job_id in JOB_IDS:
        spec = dict(SCHEDULES[job_id])
        if job_id == "cohort_batch":
            # 快照可能陈旧(只在 start_scheduler/reschedule_cohort 刷新):以配置真源为准,
            # 保证该行与 cohort 块不可能互相矛盾。
            spec["hour"], spec["minute"] = cohort["hour"], cohort["minute"]
        rows.append(
            {
                "job_id": job_id,
                "label": JOB_LABELS[job_id],
                "schedule": spec,
                "next_fire_time": _next_fire_time(job_id),
                "last_run": last_job_run(job_id),
                "history": list_job_runs(job_id, limit=HISTORY_LIMIT),
            }
        )
    return rows


def _jobs_payload() -> dict[str, Any]:
    """状态接口全量载荷(阻塞式实现;端点经 ``asyncio.to_thread`` 调用)。"""
    _sweep_stale_running()
    settings = get_cohort_settings()
    cohort = _cohort_block(settings)
    return {
        "scheduler_running": _scheduler_running(),
        "jobs": _job_rows(cohort),
        "cohort": cohort,
    }


def _find_run(run_id: int) -> dict[str, Any] | None:
    """按 run_id 取运行历史行。

    模型层未提供按 id 的读取口(本任务不改 model.py),故经最新 1000 行的窗口内查找;
    运行历史由 ``prune_job_runs`` 按 job 保序,窗口外的旧行不可读属已知限制。
    """
    for row in list_job_runs(limit=1000):
        if int(row["run_id"]) == run_id:
            return row
    return None


# ── 端点:状态 / 补跑 / 单条运行 ──


@router.get("/jobs")
async def get_jobs() -> dict[str, Any]:
    """五任务排程 / 下次触发 / 最近运行 / 历史 + cohort 块(调度器未运行显式披露)。"""
    return await asyncio.to_thread(_jobs_payload)


@router.post("/jobs/{job_id}/run", status_code=202)
async def trigger_job(job_id: str) -> dict[str, Any]:
    """手动补跑(补漏跑):与定时触发同一入口(单飞锁 + 运行历史)。

    202 = 已执行且成功(``run_job`` 同步完成,经线程执行不阻塞事件循环);
    404 = 未知任务;409 = 已在运行 / cohort 开关关闭;500 = 任务执行失败(原因在 detail
    与运行历史,不得伪装 202)。
    """
    try:
        outcome = await asyncio.to_thread(run_job, job_id, source="manual")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail="already_running") from exc
    except CohortDisabled as exc:
        raise HTTPException(status_code=409, detail="cohort_disabled") from exc
    if outcome["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"run_failed（run_id={outcome['run_id']}）：{outcome['error']}",
        )
    return {"run_id": outcome["run_id"]}


@router.get("/runs/{run_id}")
async def get_run(run_id: int) -> dict[str, Any]:
    """单条运行(含 summary/error):补跑、定时批与长任务(backtest/probe/health)同源可查。"""
    row = await asyncio.to_thread(_find_run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return row


# ── 端点:cohort 开关与时刻 ──


@router.get("/cohort")
async def get_cohort() -> dict[str, Any]:
    """cohort 开关 / 时刻 / 预算上限 / 今日花费与成功失败。"""
    return await asyncio.to_thread(lambda: _cohort_block(get_cohort_settings()))


def _apply_cohort_update(req: CohortUpdate) -> dict[str, Any]:
    """写配置 + 即时重排 + config-change 审计行(旧值→新值)。阻塞式,由端点入线程。"""
    before = get_cohort_settings()
    if req.enabled is not None:
        set_config(COHORT_ENABLED_KEY, "1" if req.enabled else "0")
    if req.hour is not None:
        set_config(COHORT_HOUR_KEY, str(req.hour))
    if req.minute is not None:
        set_config(COHORT_MINUTE_KEY, str(req.minute))
    after = get_cohort_settings()
    # 时刻改动即时生效(无需重启);无调度器(TESTING)时返回 False,配置已落库重启即生效
    rescheduled = reschedule_cohort(after["hour"], after["minute"])
    summary = {
        "from": {key: before[key] for key in _ROOT_KEYS},
        "to": {key: after[key] for key in _ROOT_KEYS},
        "rescheduled": rescheduled,
    }
    audit_run_id = insert_job_run(
        "cohort_batch", "config-change", "ok", source="manual", summary=summary
    )
    finish_job_run(audit_run_id, status="ok")
    logger.info(
        "cohort 配置变更: %s → %s(rescheduled=%s)", summary["from"], summary["to"], rescheduled
    )
    return {
        **_cohort_block(after),
        "audit_run_id": audit_run_id,
        "rescheduled": rescheduled,
    }


@router.put("/cohort")
async def update_cohort(req: CohortUpdate) -> dict[str, Any]:
    """更新 cohort 开关/时刻(局部字段语义);返回新状态 + 审计行 id + 是否已重排。"""
    return await asyncio.to_thread(_apply_cohort_update, req)


# ── 端点:报告注册表 ──


def _positioning_of(text: str) -> str | None:
    """从报告正文判定位标签:泄漏降级(上界证据) > 通路验证;未标注 → None。"""
    if "泄漏污染下的上界证据" in text:
        return POSITIONING_UPPER_BOUND
    if "通路验证" in text:
        return POSITIONING_PATHWAY
    if re.search(r"定位[：:]\s*skill|positioning[：:]\s*skill", text):
        return POSITIONING_SKILL
    return None


def _probe_hit_rate_of(text: str) -> float | None:
    """从正文取探针方向命中率(md 渲染为百分数);缺失/「未提供」→ None(不折算 0)。"""
    match = _HIT_RATE_RE.search(text)
    return round(float(match.group(1)) / 100.0, 4) if match else None


def _reports_payload() -> list[dict[str, Any]]:
    """回测报告注册表(只读):status 徽章 + 取代者 + 定位标签 + 探针方向命中率。"""
    try:
        entries, _unstamped = collect_status_index(BACKTEST_RESULTS_DIR)
    except ValueError as exc:
        # 有缺陷的报告(如 superseded-by 缺目标)不静默跳过:整表显式报错
        raise HTTPException(status_code=500, detail=f"报告注册表存在缺陷报告:{exc}") from exc
    reports: list[dict[str, Any]] = []
    for entry in entries:
        try:
            text = Path(entry.path).read_text(encoding="utf-8")
        except OSError:
            logger.warning(
                "报告正文读取失败,定位/探针字段按缺失披露: %s", entry.path, exc_info=True
            )
            text = ""
        reports.append(
            {
                "name": Path(entry.path).stem,
                "path": entry.path,
                "status": entry.status,
                "target": entry.target,
                "positioning": _positioning_of(text),
                "probe_direction_hit_rate": _probe_hit_rate_of(text),
            }
        )
    return reports


@router.get("/reports")
async def get_reports() -> list[dict[str, Any]]:
    """回测报告注册表(``evals/backtest/results/*.md`` 的 status 头 + 披露摘要)。"""
    return await asyncio.to_thread(_reports_payload)


# ── 端点:长任务(回测 / 探针 / 健康检查) ──


def _trim_backtest_summary(report: dict[str, Any]) -> dict[str, Any]:
    """报告 → 运行历史 summary(裁剪版)。

    实施计划 §Task 4 的裁剪清单按**字段路径**落地为嵌套 JSON:
    ``conclusion`` / ``positioning`` / ``n_sample`` / ``leakage_probe.direction_hit_rate``
    / ``perf_table.system.Sharpe``;另补 ``batch_kind`` / ``n_consistent`` /
    ``clean_window`` / 探针三态读数 / ``report_paths``——逐标的一致率明细不进 summary,
    完整报告在 md/json(``report_paths`` 指路)。
    """
    probe = report.get("leakage_probe") or {}
    system = (report.get("perf_table") or {}).get("system") or {}
    return {
        "batch_kind": report.get("batch_kind"),
        "conclusion": report.get("conclusion"),
        "positioning": report.get("positioning"),
        "n_sample": report.get("n_sample"),
        "n_consistent": report.get("n_consistent"),
        "clean_window": report.get("clean_window"),
        "leakage_probe": {
            key: probe.get(key)
            for key in (
                "state",
                "direction_hit_rate",
                "unknown_ratio",
                "threshold",
                "probe_n",
                "probe_window",
                "downgraded",
            )
        },
        "perf_table": {"system": {"Sharpe": system.get("Sharpe")}},
        "report_paths": report.get("report_paths"),
    }


def _trim_probe_summary(reading: dict[str, Any]) -> dict[str, Any]:
    """探针读数 → summary:三态读数 + 逐窗口明细保留,逐题 ``details`` 不进(体积大且非披露面)。"""
    return {
        key: reading.get(key)
        for key in (
            "state",
            "probe_n",
            "questions_per_ticker",
            "direction_hit_rate",
            "magnitude_hit_rate",
            "event_hit_rate",
            "unknown_ratio",
            "threshold",
            "downgraded",
            "probe_window",
            "per_window",
            "probes_missing",
        )
    }


def _trim_health_summary(reading: dict[str, Any]) -> dict[str, Any]:
    """健康检查读数本身即门禁披露面(体量小),原样入 summary。"""
    return reading


_TASK_SUMMARY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "backtest": _trim_backtest_summary,
    "probe": _trim_probe_summary,
    "health": _trim_health_summary,
}


def _finish_run_safely(run_id: int, **kwargs: Any) -> None:
    try:
        finish_job_run(run_id, **kwargs)
    except Exception:  # noqa: BLE001 - 收尾落库失败只记日志(锁必须照常释放)
        logger.exception("长任务终态落库失败 run_id=%s", run_id)


def _run_task(kind: str, run_id: int, kwargs: dict[str, Any]) -> None:
    """后台线程体:跑长任务 → 落终态;任何失败都不向线程外抛(旁路铁律)。"""
    try:
        try:
            func = _resolve_batch_func(_TASK_FUNC_NAMES[kind])
            result = func(**kwargs)
            summary = (
                _TASK_SUMMARY[kind](result) if isinstance(result, dict) else {"result": str(result)}
            )
        except Exception as exc:  # noqa: BLE001 - 任务失败落历史,线程不得炸进程
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "ops 长任务失败 kind=%s run_id=%s: %s", kind, run_id, error, exc_info=True
            )
            _finish_run_safely(run_id, status="failed", error=error)
            return
        _finish_run_safely(run_id, status="ok", summary=summary)
        logger.info("ops 长任务完成 kind=%s run_id=%s", kind, run_id)
    finally:
        _KIND_LOCKS[kind].release()


def _spawn_task(kind: str, kwargs: dict[str, Any]) -> int:
    """单飞 + 开运行行 + 起后台线程;同类任务已在运行 → 409(阻塞式,由端点在调用)。"""
    lock = _KIND_LOCKS[kind]
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="already_running")
    try:
        run_id = insert_job_run(kind, "manual", "running", source="manual")
    except Exception:
        lock.release()
        raise
    threading.Thread(
        target=_run_task,
        args=(kind, run_id, kwargs),
        name=f"ops-{kind}-{run_id}",
        daemon=True,
    ).start()
    return run_id


async def _dispatch(kind: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """派发长任务:立即 202(不阻塞事件循环),结果经 ``GET /runs/{run_id}`` 读取。"""
    run_id = await asyncio.to_thread(_spawn_task, kind, kwargs)
    return {"run_id": run_id}


async def _preflight_formal(req: BacktestRequest) -> dict[str, Any]:
    """正式批同步前置门禁(**任何回放之前**):预登记 → 抽样 + 干净窗口。

    返回 ``prepare_backtest`` 的取数结果,随任务透传(不重复抽样/取数);
    不过时抛 ``MissingPreregistrationError`` / ``CleanWindowError``,由端点翻 409。
    """
    assert_preregistered(
        PREREGISTER_DIR,
        name_contains=PREREGISTER_NAME_CONTAINS,
        required_fields=OUTCOME_REQUIRED_FIELDS,
    )
    prepare = _resolve_batch_func("prepare_backtest")
    return await asyncio.to_thread(
        prepare,
        batch_kind=req.batch_kind,
        codes=req.codes,
        per_regime=req.per_regime,
        as_of=req.as_of,
    )


@router.post("/backtest", status_code=202)
async def trigger_backtest(req: BacktestRequest) -> dict[str, Any]:
    """发起回测批(通路验证 / 正式)。

    202 = 已派发(结果经 ``/runs/{run_id}`` 与报告注册表查看);409 = 门禁拒绝(预登记
    缺失/无效、干净窗口未过)或同类批已在运行;422 = 参数非法。
    """
    if req.batch_kind not in ("pathway", "formal"):
        raise HTTPException(status_code=422, detail=f"未知批次类型: {req.batch_kind!r}")
    if not req.codes:
        raise HTTPException(status_code=422, detail="codes 不得为空")
    kwargs: dict[str, Any] = {
        "batch_kind": req.batch_kind,
        "codes": req.codes,
        "per_regime": req.per_regime,
        "repeats": req.repeats,
        "as_of": req.as_of,
    }
    if req.batch_kind == "formal":
        try:
            kwargs["prepared"] = await _preflight_formal(req)
        except MissingPreregistrationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - 只把干净窗口拒绝翻 409,其余原样上抛
            if not _is_clean_window_refusal(exc):
                raise
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _dispatch("backtest", kwargs)


@router.post("/probe", status_code=202)
async def trigger_probe(req: ProbeRequest) -> dict[str, Any]:
    """发起泄漏探针单跑(烧钱动作:前端已确认);结果经 ``/runs/{run_id}`` 读三态读数。"""
    if not req.codes:
        raise HTTPException(status_code=422, detail="codes 不得为空")
    return await _dispatch(
        "probe",
        {
            "codes": req.codes,
            "decision_date": req.decision_date,
            "window_days": req.window_days,
            "n_tickers": req.n_tickers,
            "seed": req.seed,
        },
    )


@router.post("/health", status_code=202)
async def trigger_health() -> dict[str, Any]:
    """发起 outcome 收口健康检查(只读;门禁读数与阈值随结果披露)。"""
    return await _dispatch("health", {})
