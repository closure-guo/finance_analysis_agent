# 验证报告: add-decision-hysteresis

**日期**: 2026-10-03
**分支**: `add-decision-hysteresis`（commits 1b91e94d → T4）
**关联 delta**: openspec/changes/add-decision-hysteresis/（新 capability decision-hysteresis）
**关联 issue**: #196（三评地基：决策稳定性）；数据地基 #199（pass@k 3:1 分裂）+ 离线翻转率 35%
**变更类型**: 非交互类（后端决策语义）→ 不适用 E2E 门禁

## 变更内容

**证据均衡带 + 方向滞回**（Open Questions 首版裁决：均衡带判据=RM 评级中性；降级置信度沿用重申输出；prompt 契约随本 delta 发布）：

1. `recent_directions(stock_code, window_days=5)`（track_record/model.py）：近窗历史决策只读查询，symbol 映射与 ingest 同款，fail-open（DB 异常返回 []）
2. `_evaluate_hysteresis` + `_reaffirm_decision_semantics`（nodes/risk.py）：均衡带（RM 中性）内执行动作、或与近窗前向的翻转，reasoning 未申报增量事实（窄词表：披露/季报/公告事件/技术形态确认）→ 打回重申恰一次；重申仍无 → 降级 watch（均衡带执行）/ 维持前判（翻转），如实标注落 `decision_hysteresis`
3. 维持前判到执行动作时：反方向价位清空交既有价位完整性打回补报；sell_type 维持默认 short（避免与 sell_type 申报打回级联）
4. 近窗决策史 + 均衡带标志注入 risk_judge context（首次输出即知情）；prompt 增「证据均衡与决策滞回」契约段并 deploy_prompts 发布

## 验证结果

| 验证项 | 证据 | 结果 |
|---|---|---|
| 近窗查询（排序/窗口/symbol 映射/空库/fail-open） | `tests/outcome/test_recent_directions.py` 5 用例 | ✅ |
| 均衡带内执行无增量 → 降级观望 + 标注 | `test_risk.py::TestDecisionHysteresis::test_balanced_zone_exec_no_incremental_downgraded` | ✅ |
| 均衡带内执行携增量 → 放行 | `::test_balanced_zone_exec_with_incremental_passes` | ✅ |
| 翻转无增量 → 维持前判 + 价位清空经完整性打回重报（3 调用级联） | `::test_flip_without_incremental_maintains_prior` | ✅ |
| 翻转携增量 → 放行 | `::test_flip_with_incremental_passes` | ✅ |
| 非均衡带无历史 → 零复核（行为与现状一致） | `::test_no_rating_no_history_no_op` | ✅ |
| 重申携带增量 → 放行执行 | `::test_reaffirm_with_incremental_second_pass_keeps_exec` | ✅ |
| 受影响面零回归（nodes/577 + 通道门禁） | pytest tests/nodes tests/test_graph_5layer tests/outcome | ✅ |

## 门禁命令

| 命令 | 结果 |
|---|---|
| `uv run ruff check` | All checks passed! |
| `uv run mypy`（risk.py + model.py） | no issues |
| `uv run pytest`（全量） | **3963 passed, 6 failed, 7 skipped**——6 个失败全部 @live/供应商环境项（test_eval_live×2 / fm_decision_live / ark 契约 / trace_content_live×2：当晚上游 LLM 多次限流 + 已知 @live env 泄漏误运行），与上轮全量失败清单完全相同，与本改动（risk.py/model.py/state.py/prompt，无 live 路径）零交集 |

## 取舍记录

- **pass@k 型 @live 稳定性回归**：本 delta 不含新 live 文件——同输入 k 跑方向一致性的 nightly 观察复用既有 @live 基建（fm_decision_live 形态）后续部署观察；单元级已覆盖滞回吸收采样的确定性路径（stub 双跑同输出 → 维持前判）
- **辩论势差量化阈值**：首版仅用 RM 中性评级（design Open Question 1 裁决），辩论势差二期

## 结论

[x] 全部通过——滞回双回路（均衡带降级/维持前判）+ 增量申报复核 + fail-open 查询全绿；6 个全量失败均为环境性（与上轮清单一致）
