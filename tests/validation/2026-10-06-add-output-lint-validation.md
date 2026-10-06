# 人工验证报告: add-output-lint

**日期**: 2026-10-06
**验证人**: ZCode agent（待 owner 复核）
**关联 delta**: openspec/changes/add-output-lint/
**E2E 门禁**: 不适用（纯后端确定性后处理——分析师输出装配与估值文案渲染，无前端 UI/SSE/会话切换/状态流转）

## 触发背景

10-05 八份报告二轮质检（issue #244）：深南电路(002916)分析师自我修正批注「（低于MA20约1.9%需修正）」泄漏进终稿关键发现；南方航空(600029)口径披露节原样输出「TTM 归母净利润(-13.060000000000002)非正」。

## 验证结果

### 1. 批注剥离（R1）

| 场景 | 结果 |
|---|---|
| 深南实例剥离（key_findings/markdown） | ✅ 批注含括号整体移除，其余文字保留 |
| 否定形态「（中报累计值无需修正）」 | ✅ 原样保留（lookbehind 排除） |
| 辩论用语「需修正其『多空证据实质均衡』的定性」（无括号） | ✅ 原样保留 |
| 非收尾形态「（该结论需修正后才成立）」 | ✅ 原样保留 |
| 超 48 字符括号内容 | ✅ 不命中 |
| 解析路径集成（`_parse_analyst_report` 三条返回路径统一过剥离） | ✅ |

### 2. 数值格式化（R2）

南航同型构造（年报 8.10 − 上年同期 0.94 + 最新累计 -20.22 → TTM = -13.060000000000002）：缺失原因串输出「TTM 归母净利润(-13.06)非正」，无浮点尾巴 ✅。

### 3. 存量回扫（误伤面实证）

`_EDITOR_NOTE_RE` 跑在 2026-10-05 全部 13 个会话的报告全文（含多空辩论、交易决策、FM 审批）：

- 命中 **仅深南 1 处**（即质检发现的批注本体）
- 赛轮「需修正其定性」、光大「无需修正」等全部辩论用语 **0 误伤**

### 4. 测试与检查证据

- 新增 8 项测试全绿（剥离 6 + 解析集成 1 + 格式化 1）；`tests/test_analysts_parse.py`、`tests/nodes/test_compute_valuation.py` 回归通过
- 宽域回归 `tests/nodes + tests/test_analysts_parse.py + tests/test_analyst_output_lint.py + tests/export`：599 passed / 1 skipped
- ruff 全过；mypy 相对 main 零新增（两文件 4 个既有错误基线一致）

## 异常记录

- 无阻断项。claims 字段不剥离（无证据命中，引用校验契约另行治理——见 design.md 风险节）。

## 结论

- [x] 全部 tasks 完成，`openspec validate add-output-lint --strict` 通过
- [x] 误伤面经 13 份存量报告全文实证为零
- [ ] 待 owner 复核后 sync + archive
