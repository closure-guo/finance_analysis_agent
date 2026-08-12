"""scheduler 挂载:TESTING/env 禁用、cron 注册、启停、job 异常不传播、失败重试。"""

import os
from unittest.mock import MagicMock, patch

from finance_agent.outcome.scheduler import start_scheduler, stop_scheduler


class TestStartGating:
    @patch.dict(os.environ, {"TESTING": "1"})
    def test_testing_disables(self):
        assert start_scheduler() is None

    @patch.dict(os.environ, {"DECISION_SETTLE_ENABLED": "0", "TESTING": ""})
    def test_env_disables(self):
        assert start_scheduler() is None

    @patch.dict(os.environ, {"TESTING": "", "DECISION_SETTLE_ENABLED": "1"})
    @patch("finance_agent.outcome.scheduler.BackgroundScheduler")
    def test_registers_weekday_1600_cron(self, mock_sched_cls):
        sched = MagicMock()
        mock_sched_cls.return_value = sched
        result = start_scheduler()
        assert result is sched
        _, kwargs = sched.add_job.call_args
        trigger = (
            sched.add_job.call_args.args[1]
            if len(sched.add_job.call_args.args) > 1
            else kwargs.get("trigger")
        )
        # CronTrigger: 工作日 16:00(锁语义,不锁 __str__ 格式)
        assert "16" in str(trigger)
        assert "mon-fri" in str(trigger)
        sched.start.assert_called_once()


class TestStop:
    def test_stop_none_safe(self):
        stop_scheduler(None)  # 不抛异常

    def test_stop_calls_shutdown(self):
        sched = MagicMock()
        stop_scheduler(sched)
        sched.shutdown.assert_called_once_with(wait=False)


class TestJobIsolation:
    @patch.dict(os.environ, {"TESTING": "", "DECISION_SETTLE_ENABLED": "1"})
    @patch("finance_agent.outcome.scheduler.BackgroundScheduler")
    @patch("finance_agent.outcome.scheduler.time.sleep")
    def test_job_wrapper_swallows_exceptions(self, mock_sleep, mock_sched_cls):
        """job 内部异常不传播到 scheduler(旁路铁律);sleep 打桩避免真实退避等待。"""
        sched = MagicMock()
        mock_sched_cls.return_value = sched
        start_scheduler()
        job_fn = sched.add_job.call_args.args[0]
        with patch(
            "finance_agent.outcome.scheduler.settle_open_decisions",
            side_effect=RuntimeError("boom"),
        ):
            job_fn()  # 不抛异常


class TestJobRetry:
    @patch.dict(os.environ, {"TESTING": "", "DECISION_SETTLE_ENABLED": "1"})
    @patch("finance_agent.outcome.scheduler.BackgroundScheduler")
    @patch("finance_agent.outcome.scheduler.time.sleep")
    def test_job_retries_3_times_with_backoff(self, mock_sleep, mock_sched_cls):
        """job 意外异常重试 3 次(指数退避),全失败记 ERROR 不传播。"""
        sched = MagicMock()
        mock_sched_cls.return_value = sched
        start_scheduler()
        job_fn = sched.add_job.call_args.args[0]
        with patch(
            "finance_agent.outcome.scheduler.settle_open_decisions",
            side_effect=RuntimeError("boom"),
        ) as mock_settle:
            job_fn()  # 不抛异常
        assert mock_settle.call_count == 3
        assert mock_sleep.call_count == 2  # 3 次尝试间 2 次退避

    @patch.dict(os.environ, {"TESTING": "", "DECISION_SETTLE_ENABLED": "1"})
    @patch("finance_agent.outcome.scheduler.BackgroundScheduler")
    @patch("finance_agent.outcome.scheduler.time.sleep")
    def test_job_retry_succeeds_on_second_attempt(self, mock_sleep, mock_sched_cls):
        sched = MagicMock()
        mock_sched_cls.return_value = sched
        start_scheduler()
        job_fn = sched.add_job.call_args.args[0]
        with patch(
            "finance_agent.outcome.scheduler.settle_open_decisions",
            side_effect=[RuntimeError("boom"), {"settled": 1}],
        ) as mock_settle:
            job_fn()
        assert mock_settle.call_count == 2
