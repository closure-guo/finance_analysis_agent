"""#133 回归护栏：测试期间运行时数据库必须隔离到临时目录。

背景（incident 031）：tests/test_deep_trace_root.py::TestRunGraphStreamingEvalFullData
调用真实 api._run_graph_streaming（仅图被 patch，落库挂点是真的）且未隔离 DB——
每次跑套件都往开发库 data/sessions.db 写一行 600519 buy/0.7 假决策
（9/7–9/22 累计 66 行，指纹 snapshot_hash=ffc27e76…）。

同类先例：conftest 的 _isolate_reports_dir（live 测试隔离 REPORTS_DIR）。
"""

from pathlib import Path


def _dev_db() -> Path:
    return Path("data/sessions.db").resolve()


def test_predictions_db_isolated_from_dev_db():
    """predictions 库（SESSIONS_DB_PATH / model._default_db_path）不得指向开发库。"""
    from finance_agent.outcome.track_record.model import _default_db_path

    resolved = Path(str(_default_db_path())).resolve()
    assert resolved != _dev_db(), (
        f"predictions 库指向开发库 {resolved}——测试期间必须隔离到临时目录（#133）"
    )


def test_session_store_db_isolated_from_dev_db():
    """会话库（session_store._DB_PATH，导入期冻结）不得指向开发库。"""
    from finance_agent import session_store

    assert session_store._DB_PATH.resolve() != _dev_db(), (
        f"会话库指向开发库 {session_store._DB_PATH}——测试期间必须隔离到临时目录（#133）"
    )
