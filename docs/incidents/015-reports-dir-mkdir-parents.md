# Incident 014: E2E timeline suite report_ready 丢失 — REPORTS_DIR 递归创建缺失

## 症状

E2E `timeline suite` 中 8 个测试在 CI 失败（#46）。关键模式：
- `thinking-timeline-pipeline.spec.ts` spec 1/2（中间态检查）通过
- spec 3（检查最终报告 `投资分析报告` 可见）超时 150s 失败
- `harden-react-path-resilience.spec.ts` 8.1/8.2 收到 `status=clarifying` 而非 `completed`
- `pipeline-hierarchical-timeline.spec.ts` 报告卡片不可见

stub pipeline 运行正常（18/18 stub 测试通过），但 final report 未到达前端。

## 根因

`src/finance_agent/nodes/output.py:32`：

```python
reports_dir.mkdir(exist_ok=True)  # 缺少 parents=True
```

`REPORTS_DIR` 环境变量在 E2E 中设为 `tmp/e2e-reports-8002`（嵌套路径），但 `tmp/` 目录在 CI 工作流中不存在。`mkdir(exist_ok=True)` 不带 `parents=True` 时，若父目录缺失抛 `FileNotFoundError`：

```
FileNotFoundError: [WinError 3] 系统找不到指定的路径。: 'tmp\\e2e-reports-8002'
```

`generate_file` 是管线末端节点（`generate_report → generate_file → END`），该异常**不在 try/except 内**，导致整个管线崩溃。管线的 `_background_consume` 的 `else` 块（正常完成路径）未执行，`report_ready` 的 `TOOL_RESULT` 从未 emit，SSE 流以 `None` sentinel 结束。

前端 /api/analyze 端点检测到 `report_ready` 未到达，将 session 状态置为 `clarifying`（`api.py:1324-1343`），所以 resilient spec 收到 `status=clarifying` 而非 `completed`。

## 诊断过程

1. 本地 E2E 复现：3 次管线分析中 spec 3 失败
2. 检查数据库发现所有 session `status=clarifying`，`failure_reason=FileNotFoundError`
3. 确认 `output.py:32` `mkdir(exist_ok=True)` 在父目录缺失时崩溃（Windows CI 工作流不含 `tmp/`）

## 修复

`output.py:32`：`mkdir(exist_ok=True)` → `mkdir(parents=True, exist_ok=True)`

与 `api.py:82` 对齐（后者已有 `parents=True`）。

## 验证

- 单元测试 `test_generate_file_creates_nested_reports_dir`：父目录不存在的嵌套路径不再崩溃
- E2E `thinking-timeline-pipeline.spec.ts` 3 spec 全部通过（19.2s vs 之前 150s 超时）
- 数据库 3 个 session 均为 `status=completed`、`report_len=1958`

## 预防

- `mkdir` 默认不创建父目录是 Python 常见陷阱（`exist_ok` 的 false sense of security）
- 代码审查应关注 `Path.mkdir` 是否加 `parents=True`
- 管线末端节点应有兜底 try/except 保护（非本 incident 范围，但值得 follow-up）
