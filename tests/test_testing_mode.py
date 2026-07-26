"""TESTING 开关与测试端点骨架的单元测试。"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_testing():
    """TESTING=1 下的测试客户端。"""
    with patch.dict(os.environ, {"TESTING": "1"}):
        # 重新 import 以触发 TESTING 常量读取
        import importlib

        import finance_agent.api as api_module

        importlib.reload(api_module)
        yield TestClient(api_module.app)


@pytest.fixture
def client_normal():
    """无 TESTING 环境下的测试客户端。"""
    # 确保 TESTING 未设
    env = {k: v for k, v in os.environ.items() if k != "TESTING"}
    with patch.dict(os.environ, env, clear=True):
        import importlib

        import finance_agent.api as api_module

        importlib.reload(api_module)
        yield TestClient(api_module.app)


class TestTestingMode:
    """TESTING 开关行为。"""

    def test_testing_constant_true_when_env_set(self, client_testing):
        """TESTING=1 时 api.TESTING 为 True。"""
        import finance_agent.api as api_module

        assert api_module.TESTING is True

    def test_testing_constant_false_when_env_not_set(self, client_normal):
        """无 TESTING 环境时 api.TESTING 为 False。"""
        import finance_agent.api as api_module

        assert api_module.TESTING is False

    def test_seed_endpoint_returns_200_in_testing_mode(self, client_testing):
        """TESTING=1 下 /api/test/seed 返回 200。"""
        resp = client_testing.post("/api/test/seed", json={"symbol": "300308"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "mode": "testing"}

    def test_reset_endpoint_returns_200_in_testing_mode(self, client_testing):
        """TESTING=1 下 /api/test/reset 返回 200。"""
        resp = client_testing.post("/api/test/reset", json={})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "mode": "testing"}

    def test_seed_endpoint_returns_404_in_normal_mode(self, client_normal):
        """无 TESTING 时 /api/test/seed 返回 404。"""
        resp = client_normal.post("/api/test/seed", json={"symbol": "300308"})
        assert resp.status_code == 404

    def test_reset_endpoint_returns_404_in_normal_mode(self, client_normal):
        """无 TESTING 时 /api/test/reset 返回 404。"""
        resp = client_normal.post("/api/test/reset", json={})
        assert resp.status_code == 404

    def test_health_endpoint_works_in_both_modes(self, client_testing, client_normal):
        """/api/health 在两种模式下都返回 200。"""
        resp_t = client_testing.get("/api/health")
        assert resp_t.status_code == 200
        assert resp_t.json() == {"status": "ok"}

        resp_n = client_normal.get("/api/health")
        assert resp_n.status_code == 200
        assert resp_n.json() == {"status": "ok"}
