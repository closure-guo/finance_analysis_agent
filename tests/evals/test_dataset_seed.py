"""Dataset:schema 合规、覆盖矩阵、幂等 seed。"""

import json
from unittest.mock import MagicMock

from evals.dataset_seed import DATASET_NAME, load_items, seed


class TestDatasetItems:
    def test_schema_and_coverage_matrix(self):
        items = load_items()
        assert 15 <= len(items) <= 20
        categories = [it["metadata"]["category"] for it in items]
        for cat, lo, hi in [
            ("deep_typical", 5, 6),
            ("deep_edge", 2, 3),
            ("quick", 3, 4),
            ("follow_up", 2, 3),
            ("clarify", 1, 2),
        ]:
            assert lo <= categories.count(cat) <= hi, f"{cat}: {categories.count(cat)}"
        for it in items:
            assert it["input"]["query"] and it["input"]["mode"]
            assert it["metadata"]["category"] and it["metadata"]["source"]

    def test_expected_has_no_time_sensitive_numbers(self):
        # spec「expected 不含时效数值」:不允许出现金额/百分比形态
        import re

        for it in load_items():
            text = json.dumps(it["expected_output"], ensure_ascii=False)
            assert not re.search(r"\d+(\.\d+)?\s*(亿|万|%)", text), text


class TestSeed:
    def _client(self, existing_keys=()):
        client = MagicMock()
        ds = MagicMock()
        ds.items = [MagicMock(input={"query": q, "mode": m}) for (q, m) in existing_keys]
        client.get_dataset.return_value = ds
        return client

    def test_creates_all_on_empty(self):
        client = self._client()
        result = seed(client=client)
        assert result["created"] == 16
        assert result["skipped"] == 0

    def test_idempotent_on_rerun(self):
        # spec「幂等建库」:全部已存在 → 0 created,不重复
        keys = [(it["input"]["query"], it["input"]["mode"]) for it in load_items()]
        client = self._client(existing_keys=keys)
        result = seed(client=client)
        assert result["created"] == 0
        assert result["skipped"] == 16
        client.create_dataset_item.assert_not_called()

    def test_creates_dataset_when_missing(self):
        client = MagicMock()
        client.get_dataset.side_effect = Exception("not found")
        ds = MagicMock()
        ds.items = []
        client.create_dataset.return_value = ds
        result = seed(client=client)
        client.create_dataset.assert_called_once()
        assert client.create_dataset.call_args.kwargs["name"] == DATASET_NAME
        assert result["created"] == 16

    def test_no_client_returns_error(self):
        result = seed(client=None)
        assert result["created"] == 0
        assert result["error"] is not None
