# Tasks: update-arknights-ui-theme

- [x] 明暗双主题设计令牌换装：明日方舟 UI 色卡为主、罗德岛阵营色点缀、历史品牌紫全量清除（frontend/src/index.css）
- [x] 主题调色板冻结测试先行（themePalette.test.ts：旧值 4 红 → 新值 4 绿，TDD 证据见设计文档）
- [x] 品牌色双源收敛：tailwind.config 品牌色改引 CSS 变量；Charts.tsx 回退值同步色卡并导出 cssVar
- [x] 散落硬编码色收敛：trackRecord 三页 ECharts antd 色改从变量取值；DecisionCenter/App/trackRecord 调色板类改语义令牌类
- [x] 前端全量测试与构建通过（npm test 505/505；npm run build 含 tsc -b 通过；两处断言类名更新语义不变，已在 diff 说明）
- [x] 附带修复（均已在 proposal 披露）：TrackRecordPage 高回撤警示无效 CSS 颜色值；#115 引入的 PredictionRecord.rationale_snapshot 类型缺失
- [ ] E2E spec 已覆盖核心交互场景（**不适用**：e2e/ 基础设施未落地（P1–P4 未完成），E2E 门禁按 project-workflow §3 Step 4.5 生效状态条款豁免，见人工验证报告）
- [x] 人工验证报告落 tests/validation/（含明暗双主题截图证据；用户已浏览器预览确认「就这样」）
