import pytest

from finance_agent.data.monitoring import DataSourceMonitor


@pytest.fixture(autouse=True)
def reset():
    from finance_agent.data.monitoring import reset_monitor_for_tests

    reset_monitor_for_tests()
    yield
    reset_monitor_for_tests()


def test_hit_miss_fail_and_last_hit():
    m = DataSourceMonitor()
    m.record_hit()
    m.record_hit()
    m.record_miss()
    m.record_fail("kline")
    m.record_fail("kline")
    snap = m.snapshot()
    assert snap["hits"] == 2
    assert snap["misses"] == 1
    assert snap["fails"] == {"kline": 2}
    assert snap["last_hit"] is not None


def test_get_monitor_singleton():
    from finance_agent.data.monitoring import get_monitor

    assert get_monitor() is get_monitor()
