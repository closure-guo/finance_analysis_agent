# 人工验证报告: add-citation-display

**日期**: 2026-08-31
**验证人**: ZCode agent（GUI 自动化实测 + 组件/契约测试）
**关联 delta**: openspec/changes/add-citation-display/
**E2E 门禁**: 不适用（e2e/ 基建 P1–P4 未落地）

## 验证环境

- 后端契约测试：pytest（tests/test_citation_display.py，9 例，含临时库持久化往返）
- 前端组件测试：vitest + jsdom（src/test/citationDisplay.test.tsx，6 例）
- 浏览器：真实 Chromium + TESTING=1 stub 后端；向完成会话注入结构化引用（verified/failed 各一）后实测

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 报告携带引用数组（契约） | 契约测试 | report_ready 负载含五字段引用数组 | pytest 断言 id/claim/source/verdict/detail + 三级映射 | ✅ |
| 旧数据兼容（契约） | 契约测试 | 无引用字段正常返回缺省 | pytest：无 citations 键省略；DB 读回 None；前端 null 不渲染 | ✅ |
| 行内上标渲染 | 组件测试 | 正文 [[cite-N]] 渲染为上标，编号对应 id | 实测 2 个上标出现，标记不残留；组件测试 3 上标+编号断言 | ✅ |
| hover 预览卡（懒渲染） | 组件测试 | hover 显示 claim/来源/状态；移出卸载 | 实测 hover cite-2 出现「校验未通过[2] + claim + source + 重算说明」；未 hover 不挂载 | ✅ |
| 引用与校验列表 | 组件测试 | 编号/来源/状态色标，failed 可辨 | 实测列表 2 项：verified 绿（rgb(16,185,129)）/ failed 红（rgb(239,68,68)） | ✅ |
| 刷新恢复引用 | 实测（隐含） | 重建路径 citations 随会话数据恢复 | 上例即为刷新后选中会话（rebuild 路径）渲染 | ✅ |
| 正文锚点注入（唯一匹配） | 契约测试 | 唯一匹配注入，多义/零匹配跳过 | pytest：inject_citation_marks 3 例 | ✅ |

## 实施说明

1. 正文上标锚点采用后端注入 `[[cite-<id>]]` 标记方案（design 决策 1 延伸）：`inject_citation_marks` 对唯一出现的 claim 文本注入标记，前端只做标记→上标渲染，避免两端各解析 Markdown 导致编号漂移。
2. 引用数据落库 sessions.citations 列（JSON，NULL=旧会话），刷新后引用仍可见；STUB 管线无 Claim 产出，真实 LLM 报告的引用需真钥匙环境验证（⏭ 不适用项）。

## 异常记录

无阻塞异常。

## 结论

[x] 契约/渲染/兼容全部通过（前端 421 + 后端 9 测试全绿）
[ ] 真实 LLM 报告的引用展示待真钥匙环境抽查；E2E 门禁待基建
