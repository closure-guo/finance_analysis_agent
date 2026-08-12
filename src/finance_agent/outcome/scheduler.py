"""日批结算定时任务(design 决策 6:APScheduler in-process,单 worker 无竞争)。

每个工作日 16:00(收盘后)触发 settle_open_decisions。
TESTING=1 或 DECISION_SETTLE_ENABLED=0 时禁用;job 异常不传播(旁路铁律)。
失败重试:意外异常指数退避重试 3 次(5s/20s,time.sleep 低频日批足够),
全失败记 ERROR 等下交易日;job 内 settle_open_decisions 幂等,重跑安全。
注:定时任务框架选型建议人工落 ADR(design 决策 6 注),agent 不自建 ADR。
"""

from __future__ import annotations

import logging
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from finance_agent.outcome.job import settle_open_decisions

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3


def _settle_job() -> None:
    """scheduler 入口:全部异常吞掉(旁路铁律),意外异常指数退避重试 3 次。"""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = settle_open_decisions()
            logger.info("decision settle job 完成: %s", result)
            return
        except Exception as e:  # noqa: BLE001
            if attempt < _MAX_ATTEMPTS - 1:
                backoff = 5 * (4**attempt)  # 5s / 20s
                logger.warning(
                    "decision settle job 第 %d 次失败(%s),%ds 后重试",
                    attempt + 1,
                    e,
                    backoff,
                )
                time.sleep(backoff)
            else:
                logger.exception("decision settle job 重试 3 次全部失败(下交易日再试)")


def start_scheduler() -> BackgroundScheduler | None:
    """启动日批 scheduler;TESTING/禁用时返回 None。"""
    if os.getenv("TESTING") == "1" or os.getenv("DECISION_SETTLE_ENABLED") == "0":
        return None
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _settle_job,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone="Asia/Shanghai"),
        id="decision_settle_daily",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("decision settle scheduler 已启动(工作日 16:00)")
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler | None) -> None:
    """关闭 scheduler(None 安全)。"""
    if scheduler is not None:
        scheduler.shutdown(wait=False)
