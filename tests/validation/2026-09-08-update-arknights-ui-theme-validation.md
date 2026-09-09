# 人工验证报告: update-arknights-ui-theme

**日期**: 2026-09-08
**验证人**: 用户（会话内浏览器预览确认「就这样」）+ agent 浏览器实测（明暗双主题截图与计算样式核对）
**关联 delta**: openspec/changes/update-arknights-ui-theme/
**E2E 门禁**: 不适用——`e2e/` 基础设施未落地（P1–P4 未完成），按 project-workflow §3 Step 4.5 生效状态条款豁免；以全量前端单测 + 浏览器实测承担门禁。

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 深色主题整体映射 | 否（截图核对） | 深灰面板 #2F3132 底、纯白 #FCFBFB 文字、强调蓝 #228EBF 按钮/气泡/标签 | 截图核对符合（会话视图：用户气泡、打开报告按钮、深度分析标签均为强调蓝） | ✅ |
| 浅色主题整体映射 | 否（截图核对） | #FCFBFB 画布、罗德岛黑正文、强调蓝主色 | 截图核对符合（见 light-session-view.png） | ✅ |
| 主题三态切换机制 | 否（既有单测覆盖 + 实测） | 浅色/深色/跟随系统切换并持久化 | 预览中反复切换正常；`darkModeShortcuts` 单测通过（505/505 内） | ✅ |
| 运行态亮青点缀 | 否（抽查） | 分析节点运行态为亮青蓝边框+辉光 | 令牌 `--status-primary-default: #3FC6E0`（深色）生效，node-running 样式引用该变量，抽查符合 | ✅ |
| 图表色随主题变量 | 否（机制未改） | 图表 option 从变量取色，色卡系列色生效 | 机制未动，仅回退值同步；`chartsMarkLine` 等图表单测通过 | ✅ |
| 历史品牌紫清除 | 否（冻结测试） | #4B3FE3/#6C5FF0/#8F84F5 不出现于前端源码 | `themePalette.test.ts` 断言通过；残留扫描（antd 色值 + 调色板类）为零 | ✅ |
| 既有测试无修改通过 | 否 | 全量套件不修改断言语义通过 | 505/505 通过；2 处断言锚点随令牌化迁移（语义未放宽，diff 已说明） | ✅ |
| 主观项：整体观感 | 否 | 符合明日方舟 UI 气质 | 用户浏览器预览后确认「就这样」 | ✅ |

**证据文件**: `tests/validation/2026-09-08-arknights-ui-theme/dark-session-view.png`、`light-session-view.png`（预览环境 http://localhost:5174/，浏览器计算样式核对：新建分析按钮 `rgb(42,91,168)` → 换装后随令牌）。

## 异常记录

1. `npm run build` 在 HEAD 上即失败（#115 合并引入 `PredictionRecord.rationale_snapshot` 类型缺失，与本次无关）——已随本次以一行可选字段修复，全量构建转绿。
2. `TrackRecordPage` 高回撤警示色因历史 bug 从未实际生效（style 中误用类名字符串）——随本次收敛修复。

## 结论

- [x] 全部通过，可 archive
- [ ] 存在失败项，需修复后重新验证
