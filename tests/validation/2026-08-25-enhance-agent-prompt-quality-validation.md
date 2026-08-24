# 人工验证报告: enhance-agent-prompt-quality

**日期**: 2026-08-25
**验证人**: agent（自动化验证）+ 待真人抽检（LLM 输出质量项）
**关联 delta**: openspec/changes/enhance-agent-prompt-quality/
**E2E 门禁**: 不适用（非交互类变更——纯后端提示词调整，无前端 UI/SSE/会话切换/状态流转）

## 变更类型判别

按 `docs/project-workflow.md` §2：不涉及前端 UI、SSE 流式、会话切换、状态流转中任一者 → 纯后端逻辑变更，不适用 §3.5 E2E 门禁。人工验证聚焦 LLM 输出质量项。

## 验证结果

| Scenario | 验证方式 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 分析师提示词含反幻觉硬规则+方法论 | 契约测试（tests/test_prompt_contracts.py） | 4 个分析师 .md 含 `## 分析方法论`+`## 反幻觉硬规则`+`数据不足` | 32 个契约用例全绿 | ✅ |
| 辩论者提示词含对抗性指令 | 同上 | bull/bear/risk_debater 含 `## 辩论纪律`+`反驳`+`对方` | 契约用例通过 | ✅ |
| 决策层含语义契约 | 同上 | trader/risk_judge/fund_manager 含 `## 决策语义` 及各档位语义 | 契约用例通过 | ✅ |
| research_manager 评级表态 | 同上 | 含 `## 评级表态`+看多/看空/中性 | 契约用例通过 | ✅ |
| deep_mode/report 摘要仅基于输入 | 同上 + report.py 源码断言 | 含 `## 输出约束`+`仅基于`+`不得引入` | 契约用例通过 | ✅ |
| 硬编码收敛 | 契约测试 + 全仓 grep | nlp.py 不存在、股票解析提示词仅 react_agent.py 一处、REACT_SYSTEM_PROMPT 移除 | 契约用例通过，grep 0 残留 | ✅ |
| 输出 JSON schema 不变 | 代码审查 + 全量回归 | AnalystReport/TradeDecision/DebateMessage 结构未变（提示词改动不触碰 schema） | 全量 1240 非 live 用例通过；每任务独立 reviewer 确认 schema/state/节点结构零改动 | ✅ |
| 报告内容质量提升（辩论对抗、决策语义） | 待真机抽检 | 辩论出现针对对方论点的回应；trader confidence/position_size 有语义 | **未执行**：本机无 LLM_API_KEY/DEEPSEEK_API_KEY，真实 LLM 管线无法运行 | ⏸ 待真机 |
| @live 套件 | 基线对比 | 4 个 @live 用例（真实 AKShare/LLM）| 基线 main 同样失败（既有环境问题，非本 delta 引入） | ⏸ 既有 |

## 异常记录

- **真机抽检未执行**：环境无 API key（`.env` 无 DEEPSEEK_API_KEY/LLM_API_KEY），`tests/e2e/test_5layer_pipeline.py` 与人工抽查"报告内容质量提升"无法运行。需在配置好 key 的环境补做：触发一份深度报告，抽查 (a) 输出 schema 与改动前一致；(b) 辩论内容出现"针对对方论点"回应；(c) trader reasoning 每条例据有 evidence_ref 且数值与来源一致；(d) 聚焦摘要无材料外数值。
- **mypy 69 错误**：全部为基线既有（main 分支复跑同为 69 errors），本 delta 未引入新类型错误。

## 结论

[ ] 全部通过，可 archive
[ ] 存在失败项，需修复后重新验证
[x] 自动化验证全部通过；LLM 输出质量项待真机环境补抽检（不阻塞合并——prompt 内容契约已由 32 个契约用例锁定，后续在配置 key 的环境中运行 @live 套件补证，存档时注明）

> 说明：依照 verification-before-completion 纪律，本报告如实区分"已自动化验证"与"待真机验证"两类证据，未将 LLM 输出质量声称作为已验证项。