# 人工验证报告: update-agent-prompt-cycle-fit

**日期**: 2026-08-25
**验证人**: agent（自动化验证）+ 待真机复核（以下标 ⏸ 项）
**关联 delta**: openspec/changes/update-agent-prompt-cycle-fit/
**E2E 门禁**: 不适用（非交互类变更——纯后端数据层 + prompt 调整）

## 验证结果

| Scenario | 验证方式 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 时效守卫：fresh 指标 | 单测（TestMacroFreshness） | M2/CPI 当月数据 → freshness=fresh + as_of_date | 断言通过 | ✅ |
| 时效守卫：stale 指标 | 单测 | PMI 5 个月前 → freshness=stale + as_of_date 解析年份 | 断言通过 | ✅ |
| 时效守卫：拉取失败 | 单测 | `_call_ak` 返回 None → 各指标空列表 | 断言通过 | ✅ |
| context 消费 freshness | 单测（TestBuildMacroContext） | stale 指标确定性附加"数据滞后至 YYYY-MM"标注；fresh 不打扰 | 断言通过 | ✅ |
| 契约测试 | pytest | 既有 32 契约 + 4 周期适配断言全绿 | 36 passed | ✅ |
| 全量回归（非 live） | pytest `-m "not live"` | 0 失败 | **1243 passed, 2 skipped, 0 failed** | ✅ |
| ruff / mypy | 命令 | clean / 无新增错误 | ruff All passed；mypy 69 errors 与基线同数（既有） | ✅ |
| 真实链路时效核查 | 实测 `_call_ak(ak.macro_china_pmi)` | 生产路径 PMI 返回 2026-07（fresh，不会误标 stale） | 确认：pmi 223 行、最新"2026年07月份" | ✅ |
| M1/M2 剪刀差在真实报告的体现 | 真机抽查 | 宏观分析出现剪刀差表述 | **未执行**：无 LLM key | ⏸ |
| 强趋势钝化提示的报告体现 | 真机抽查 | 技术面强趋势股不因 RSI 超买直接判反转 | **未执行**：无 LLM key | ⏸ |

## 勘误记录

- 早前评估曾判定"PMI/CPI 接口滞后约一年"（依据 `macro_china_pmi_yearly` 接口返回 2025 年数据）。实测发现**生产路径 `fetch_macro_indicators` 使用 `macro_china_pmi`（月度接口）返回 2026-07**，并不滞后。本轮守卫的价值因此从"修复当前事故"转为"防御未来不同接口时效不一/数据源漂移"——守卫仍必要（spec 场景"各指标独立标记、不误用相邻指标日期"即覆盖此类风险），但 delta 描述中的"当前滞后事故"表述已在设计文档标注修正。

## 异常记录

- 4 个 `@live` 用例（test_outcome_live/test_trace_content_live）为既有网络环境失败（基线同样），不在本 delta 范围。

## 结论

[x] 自动化验证全部通过；真机 LLM 输出抽查（剪刀差/钝化体现）待有 key 环境补做
[ ] 全部通过，可 archive（自动化证据充分；⏸ 项不阻塞合并，prompt 契约已由测试锁定）

> 说明：按 verification-before-completion 纪律，本报告如实区分"已自动化验证"与"待真机验证"，未将 LLM 输出质量作为已验证项声称。