# Proposal: add-decision-hysteresis

## Why

决策稳定性问题双实锤（issue #196）：离线历史翻转率 35%（81 对中 28 翻转，全为执行↔观望摇摆）；pass@k 现场实验同输入 4 有效跑 3:1 分裂（watch/watch/sell/watch）——**纯采样方差**（输入完全相同），置信度判别力弱（sell@50% vs watch@55-62%）。证据均衡带（如拓荆：85.9 倍 PE vs 净利 +1328% 对峙）的单次方向输出无信息量，日批场景用户建议反复横跳（600515 九天 3 翻转实证），策略不可执行。owner 已批滞回机制（2026-10-02「都批」）。

## What Changes

- **证据均衡带显式化**：Research Manager 评级（看多/看空/中性）与 Bull/Bear 辩论势差进入决策上下文时，risk_judge SHALL 识别「均衡带」（判据：RM 评级为中性 或 多空辩论关键论据对峙无增量事实），均衡带内默认输出 watch/hold——执行动作（buy/sell）需要**证据增量**支撑，MUST NOT 由采样噪声触发
- **决策滞回**：同标的存在近期历史决策（decision-outcome predictions 库，窗口默认 5 个交易日）时，方向翻转（watch↔执行）SHALL 携带滞回判据进 LLM 上下文并进入输出约束——翻转必须引用**新增量事实**（新报告期披露/重大公告/技术形态破位确认，事件列表显式申报在 reasoning）；无增量事实的翻转 → 输出维持前向方向，如实标注「维持前判（无证据增量）」
- **执行侧依赖**：buy/sell 方向的仓位与退出结构按 #188 分型落地后细化（本 delta 只管方向滞回，不动参数模板）
- **可观测**：滞回判定（前向方向/窗口内历史/是否引用增量事实）落 state 键 + trace，报告不渲染额外标注

## Capabilities

### New Capabilities

- `decision-hysteresis`: 证据均衡带判定 + 方向滞回约束 + 增量事实申报

### Modified Capabilities

（无——price-level-tooling/report-decision-rendering 等不受影响；watch/hold 语义由 require-watch-hold-rationale 既有契约承载「维持前判」理由）

## Impact

- `src/finance_agent/nodes/research_manager.py`（评级势差信号）与 `nodes/risk.py`（均衡带判定 + 滞回上下文 + 输出复核）+ `nodes/debate.py`（辩论势差提取，视实现深度）
- 新 state 键：`decision_hysteresis`（前向方向/窗口历史/均衡带标志/增量事实申报）
- `src/finance_agent/outcome/track_record/model.py`：近窗历史决策查询函数（只读）
- prompts：risk_judge prompt 需增滞回约束段（须 deploy_prompts 同步）
- 测试：均衡带判定单元测 + 滞回上下文注入测 + 无增量翻转被约束的 stub 集成测 + pass@k 型稳定性回归（@live，nightly）
- 依赖：#188 分型（执行侧参数，可并行推进、后置合入）

**非交互类变更（后端决策语义）→ 不适用 E2E 门禁**
