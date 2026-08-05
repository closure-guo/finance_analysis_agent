"""验证 live E2E 测试的 REPORTS_DIR 隔离 fixture 工作。

背景：E2E 测试（test_5layer_pipeline.py / Playwright pipeline 场景）会触发
generate_file 节点写盘到 REPORTS_DIR。若不隔离，会污染 reports/ 目录
（堆积大量 600519_*_report.docx/pptx 垃圾文件）。

conftest._isolate_reports_dir autouse fixture 应对带 `live` mark 的测试
注入临时 REPORTS_DIR，使其不落到默认 `reports/`。
"""

import os

import pytest


@pytest.mark.live
def test_reports_dir_isolated_for_live_tests():
    """live mark 测试运行时 REPORTS_DIR 应指向临时目录，而非默认 reports/。"""
    reports_dir = os.environ.get("REPORTS_DIR", "reports")
    # 默认值 `reports` 表示 fixture 未生效（失败态）
    assert reports_dir != "reports", "live 测试未隔离 REPORTS_DIR，会污染 reports/ 目录"
    assert "e2e-reports" in reports_dir, (
        f"REPORTS_DIR 应指向临时 e2e-reports 目录，实际: {reports_dir}"
    )


def test_reports_dir_not_isolated_for_non_live_tests():
    """非 live mark 的普通测试不应被隔离，REPORTS_DIR 保持原样（默认 reports）。"""
    reports_dir = os.environ.get("REPORTS_DIR", "reports")
    # 普通 unit/integration 测试不应被 fixture 改写
    # （要么未设置走默认 reports，要么是外部显式设置）
    assert "e2e-reports" not in reports_dir, "非 live 测试不应被注入 e2e-reports 临时目录"
