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

    def test_seed_endpoint_creates_session_with_thinking_and_tool_calls(
        self, client_testing, tmp_path
    ):
        """POST /api/test/seed 写入含 thinking + tool_calls 的 chat_history，GET /api/sessions/{id} 可取回。

        历史会话恢复 E2E（agent-turn-box-display delta task 5.6）依赖该能力确定性构造
        含 agentTimeline 数据的历史会话。
        """
        # 隔离 DB 路径，避免污染真实 data/sessions.db
        import finance_agent.session_store as session_store_module

        with patch.object(session_store_module, "_DB_PATH", tmp_path / "test_sessions.db"):
            # tmp DB 需初始化表结构（init_db 幂等）
            session_store_module.init_db()
            payload = {
                "display_name": "历史恢复测试会话",
                "session_type": "chat",
                "chat_history": [
                    {"role": "user", "content": "帮我分析一下茅台"},
                    {
                        "role": "assistant",
                        "content": "茅台是白酒龙头。",
                        "thinking": "先理解用户意图：分析茅台基本面。",
                        "tool_calls": [
                            {
                                "name": "search_stock",
                                "args": {"query": "茅台"},
                                "result_text": "600519 贵州茅台",
                                "done": True,
                            }
                        ],
                    },
                ],
            }
            resp = client_testing.post("/api/test/seed", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert "session_id" in body, f"响应应含 session_id，实际：{body}"
            session_id = body["session_id"]

            # GET /api/sessions/{id} 应取回含 thinking + tool_calls 的 chat_history
            detail = client_testing.get(f"/api/sessions/{session_id}")
            assert detail.status_code == 200
            data = detail.json()
            assert data["display_name"] == "历史恢复测试会话"
            assert data["session_type"] == "chat"
            history = data["chat_history"]
            assert len(history) == 2
            assistant_entry = history[1]
            assert assistant_entry["role"] == "assistant"
            assert assistant_entry["thinking"] == "先理解用户意图：分析茅台基本面。"
            assert assistant_entry["tool_calls"][0]["name"] == "search_stock"
            assert assistant_entry["tool_calls"][0]["done"] is True

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
