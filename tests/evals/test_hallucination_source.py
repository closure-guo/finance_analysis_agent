"""幻觉率真值 source 校验（harden-eval-implementation-decoupling）。"""

import pytest
from evals.hallucination.measure import require_data_source, run_offline


class TestDataSource:
    def test_missing_source_rejected(self):
        with pytest.raises(ValueError, match="source"):
            require_data_source({"price": 100.0})
        with pytest.raises(ValueError, match="source"):
            run_offline("报告文本", data_map={"price": 100.0})

    def test_with_source_accepted(self):
        require_data_source({"source": "snapshot:akshare-2026-08-25", "price": 100.0})
        result = run_offline(
            "股价上涨 3%", data_map={"source": "snapshot:akshare-2026-08-25", "pct": 3.0}
        )
        assert result.rate is not None

    def test_empty_map_allowed(self):
        require_data_source({})
        require_data_source(None)
