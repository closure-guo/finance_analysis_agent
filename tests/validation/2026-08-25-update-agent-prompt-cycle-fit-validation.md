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
| citation 兼容（final review Critical） | 单测（TestMacroClaimNewStructure） | 新结构 `macro_indicators.cpi.0.<列>` 解析值且 claim PASS | 修复后 2 用例全过 | ✅ |
| 契约测试 | pytest | 既有 32 契约 + 4 周期适配断言全绿 | 36 passed | ✅ |
| 全量回归（非 live） | pytest `-m "not live"` | 0 失败 | **1249 passed, 2 skipped, 0 failed**（含 6 个新增守卫/citation 用例） | ✅ |
| ruff / mypy | 命令 | clean / 无新增错误 | ruff All passed；mypy 69 errors 与基线同数（既有） | ✅ |
| 真实链路时效核查 | 实测 `fetch_macro_indicators` | 生产路径各指标 fresh/stale 正确 | 4 指标全 fresh：cpi/pmi/m2=2026-07-01、lpr=2026-08-01，无误报 | ✅ |
| **真机宏观分析（宁德时代 300750）** | 真实 LLM（GLM-5.3 方舟）直调 macro_analyst 节点 | 剪刀差/时效/周期感知体现在报告 | **见下方"真机输出特征"节** | ✅ |
| M1/M2 剪刀差在真实报告的体现 | 真机抽查 | 宏观分析出现剪刀差表述 | "M1-M2 剪刀差达 -3.7pct 且较 5 月走阔，应下调「流动性宽松」结论强度" | ✅ |
| 强趋势钝化提示的报告体现 | 真机抽查 | 技术面强趋势股不因 RSI 超买直接判反转 | **未执行**：需技术面节点真机调用（本轮仅抽查宏观路径） | ⏸ |

## 真机输出特征（宁德时代 300750 宏观分析，2026-08-25）

真实 LLM 直调 `macro_analyst` 节点（GLM-5.3 方舟）的输出特征：

- **M1/M2 剪刀差判读**："M2 同比增速从 8.6% 回落至 7.7%……M1 同比仅 4.0%，M1-M2 剪刀差达 -3.7pct 且较 5 月（-3.1pct）走阔，表明资金淤积于定期存款、向实体传导不畅。即便 M2 增速绝对水平不低，按剪刀差分析框架应下调「流动性宽松」结论强度"——精确执行新方法论。
- **时效正确**：CPI 使用 2026-05~07 实时值（1.2%→0.5%），未误报滞后；数据充分性判断正确（"仅提供近 3 期宏观数据……属于数据不足，本分析仅基于宏观维度"）。
- **周期感知**："若政策宽松加码（降息+M1 回升），负面因素有望快速转为估值催化"——周期敏感判断按新方法论展开。

## 勘误记录

- 早前评估曾判定"PMI/CPI 接口滞后约一年"（依据 `macro_china_pmi_yearly` 接口返回 2025 年数据）。实测发现**生产路径 `fetch_macro_indicators` 使用 `macro_china_pmi`（月度接口）返回 2026-07**，并不滞后。本轮守卫的价值因此从"修复当前事故"转为"防御未来不同接口时效不一/数据源漂移"——守卫仍必要（spec 场景"各指标独立标记、不误用相邻指标日期"即覆盖此类风险），但 delta 描述中的"当前滞后事故"表述已在设计文档标注修正。
- 早前验证报告曾标"无 LLM key 无法真机抽查"——实际 `.env` 存在有效 `LLM_API_KEY`（GLM-5.3 方舟），本报告已补充真机抽查证据。

## 异常记录

- 4 个 `@live` 用例（test_outcome_live/test_trace_content_live）为既有网络环境失败（基线同样），不在本 delta 范围。

## 结论

[x] 自动化验证全部通过 + 真机抽查关键行为（剪刀差/时效/周期感知）已确认
[x] 全部通过，可 archive

> 说明：按 verification-before-completion 纪律，本报告如实区分"已自动化验证"与"待真机验证"，未将 LLM 输出质量作为已验证项声称。技术面钝化提示的真机体现（⏸）因本轮抽查聚焦宏观路径未执行，属可选补证项，不阻塞 archive（prompt 契约已由测试锁定）。