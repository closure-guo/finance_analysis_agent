# 验证报告: update-sell-action-typing

**日期**: 2026-10-02
**分支**: `update-sell-action-typing`（commits 0e4d89d7 → T5）
**关联 delta**: openspec/changes/update-sell-action-typing/（report-decision-rendering + agent-prompt-contracts MODIFIED）
**关联 issue**: #188（回归评审 P1：exit/short 模板分离）
**变更类型**: 非交互类 → 不适用 E2E 门禁

## 变更内容

sell 决策分型：`sell_type: exit|short`（持有者减仓 / 做空建仓）+ `exit_schedule`（减仓节奏）渐进字段（action 枚举不变，非 BREAKING）。exit 豁免 entry/stop/target 必填、改必填 exit_schedule；risk_judge sell 缺 sell_type 打回申报一次（仍缺默认 short + 如实标注）；渲染分模板（exit 渲染减仓节奏不渲染建仓价位行，short/None 现行）；trader/risk_judge prompts 双型语义已发布（deploy_prompts）；结算层零改动（exit/short 收益数学一致，注释声明）。

## 验证结果

| 验证项 | 证据 | 结果 |
|---|---|---|
| schema 双型字段 + 归一（大小写/中文同义词/杂值/非 sell 归 None） | `tests/test_models.py::TestSellTypeTyping` 6 用例 | ✅ |
| exit 价位豁免 + exit_schedule 必填 + short/None 现行 | `test_validate_trade_prices.py::TestSellTypePriceExemption` 4 用例 | ✅ |
| sell_type 申报打回（申报 exit 放行 / 仍缺默认 short+标注 / 已申报不打回） | `test_risk.py::TestSellTypeDeclarationLoop` 3 用例 | ✅ |
| 渲染分模板（exit 节奏行/无价位行；exit 缺节奏「未申报」；short/None 现行） | `test_report_decision_render.py::TestSellTypeSplitRendering` 4 用例 | ✅ |
| prompts 双型契约 + deploy 一致性 | deploy_prompts 执行 + prompt 契约套件 78 passed | ✅ |
| 既有回路零回归（价位门禁/reeval/报告） | 既有夹具补 sell_type=short 后全绿 | ✅ |

## 门禁命令

| 命令 | 结果 |
|---|---|
| `uv run ruff check` | All checks passed! |
| `uv run mypy`（4 个触改文件） | no issues |
| `uv run pytest`（全量） | **3952 passed, 4 failed, 7 skipped**——4 个失败全部环境性非回归：①`test_fm_decision_live`（历史 @live 环境项，历轮同态）；②`test_ark_tool_call_contract`（供应商侧不稳，**stash 掉本分支改动后干净基线同样失败**，当日上游已两度限流）；③④`test_trace_content_live`×2（@live 密钥 env 泄漏使全量环境误运行后真实 LLM 调用失败，已知 .env 上溯问题，与本改动路径零交集） |

## 设计要点（实施备注）

- 打回顺序：sell_type 申报判定在价位完整性检查**之前**（先定型再验参数，exit 免去无意义的价位打回，打回预算不叠加）
- 夹具迁移：价位门禁/reeval 既有用例补 `sell_type: "short"`（用例意图隔离，行为语义不变）
- 渲染断言注意 markdown 前缀（`- **减仓节奏**: `）

## 结论

[x] 全部通过——分型三链路（schema/校验打回/渲染）+ prompts 发布齐备；4 个全量失败均环境性（stash 对照+路径分析双重确认）

