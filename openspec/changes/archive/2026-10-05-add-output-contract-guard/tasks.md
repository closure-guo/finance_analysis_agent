# Tasks: add-output-contract-guard

- [x] 共享校验器 `output_guard.py`：泄露模式 / 中文占比 / 截断信号三类规则产出 verdict，单测以 incident 036 实测泄露样本（拓荆 171013 报告研究聚焦段）为红→绿基准
- [x] 直通不误伤单测：以中远海能 2026-10-04 14:49 干净研究聚焦样本锁定 pass-through 行为
- [x] `report.py` `_build_focus_summary` 接入校验：违约定向重试 1 次 → 仍违约走结构化兜底；移除 `raw_reasoning` 交付回退（reasoning 仅进 trace），单测覆盖 content 为空场景
- [x] `complete_text` 观测 metadata 补 `finish_reason` / `resume_count`；guard 判定结果与命中规则进 trace metadata
- [x] 人工验证报告落 `tests/validation/`：真实跑一次拓荆科技深度分析，核对交付报告研究聚焦段无泄露、无截断、置信度数字可溯源
