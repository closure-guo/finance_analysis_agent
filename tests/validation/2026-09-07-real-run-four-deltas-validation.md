# 四 delta 真实链路验证（2026-09-07，本地新代码后端 8001）

> 覆盖：calibrate-fm-approval 4.3 / data-ordering-citation-contract 3.2 /
> harden-llm-output-validation 6.5 / langfuse-trace-agent-attribution 3.2+4.6。
> 运行方式：`uv run uvicorn ... --port 8001`（当前 HEAD 代码，非 docker 旧镜像），
> POST /api/analyze 拓荆科技 688072 深度分析，session `794fc89e-918`，
> Langfuse trace `ab6d1fd2425fbbcf895b75e4aa96fa13`，报告 13813 字。

## 1. calibrate-fm-approval 4.3 — 真实链路 return→trader 重跑→报告反映改进 ✅

- **修复前置发现（本次验证抓到图级缺陷）**：`state.py` 未声明 `fund_manager_decision_reasoning`
  键，LangGraph 合并节点输出丢弃该键 → trader 重跑上下文拿不到退回意见（首跑输入与重跑
  逐字节相同 md5）。单元测试只测节点函数因此全绿。已修：state schema 声明该键 +
  `tests/test_graph_5layer.py::TestFmReturnReasoningContract` 2 例（先红后绿）。
- **修复后实跑闭环**：FM#0 decision=**return**（"缺少完整的交易决策说明与风控结论…请 T…"）
  → trader#1 重跑输入 **len 4337→4449，含「基金经理退回意见」段落**（注入生效）→
  FM#1 decision=**approve**（"已针对前次退回意见进行了修正，风险管理结论与交易决策方向一致"）。

## 2. data-ordering-citation-contract 3.2 — 引用最新期、无 2008、无重试风暴 ✅

- 报告基本面引用最新期（ROE 15.77%、营收利润高增长），**无「2008」旧期误引**。
- 宏观数据本次源不可用（如实报告"指标数据暂不可用"），非错序——排序修复由
  9 例单测覆盖（tests/test_macro_order_fix.py 等），本跑确认生产路径无回退异常。
- 管线正常完成（~4 分钟，analyst 仅 1 次重试），无重试环空转。

## 3. harden-llm-output-validation 6.5 — Layer V 正常审批 + 中文标注 + 无枚举异常 ✅

- FM approve，报告含审批中文标注（「基金经理」段落），最终报告正常出（13813 字）。
- 后端日志 0 处 ValidationError / 枚举校验异常；非法枚举加固（Literal 7 值）未误伤正常链路。

## 4. langfuse-trace-agent-attribution 3.2 + 4.6 — agent 命名、session 过滤、根 span output ✅

- generation 观测按 agent 命名（20/20），metadata 写 agent + stock_code（688072）。
- **session 过滤**：trace.sessionId=`794fc89e-918`（propagate_attributes）→ Langfuse UI
  可按 session/user 聚合并过滤。generation metadata 级 session_id 键未写入（开放项，
  功能由 trace.sessionId 覆盖）。
- **根 span output 不再 null**：修复前置 api 只写 metadata 不写 output；已修
  `_root_obs.update(metadata=…, output=_build_trace_output(accumulated))`（复用 agent_factory
  摘要构造，metadata/output 独立容错），新增 `test_deep_trace_root.py` 用例（先红后绿）。
  实跑根 trace output 8 键：stock_code/stock_name/analysis_type/final_report_summary/
  analyst_reports/trader_plan/final_trade_decision/fund_manager_decision。

## 附：本批修复提交

`68d58bf fix(evals): FM 退回理由 state 未声明致图合并丢弃 + api 根 span 补 output 摘要`
（含 state.py 声明 + 图级契约测试 2 例 + api output 写入 + 单测 1 例；回归 60+14 tests、ruff、mypy 无新增）。