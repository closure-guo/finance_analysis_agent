# Proposal: redesign-pipeline-hierarchical-timeline

## Why

深度分析管线的 UI 观感差，用户无法直观看到 agent 当前任务的执行状态：

- 6 阶段圆点粒度过粗：Layer II 含 5 个串行子节点、Layer IV 含 5 个串行子节点，全部合并为一个圆点，长时间无视觉反馈
- Layer I 分析师卡片摘要文案错位（fundamental 卡片显示技术面文案），且 4 卡片状态完全绑定 technical_analyst 单节点，不反映真实并行进度
- 各 agent 的思考横幅平铺堆叠（sentiment/macro/fundamental/技术面分析师 顺序混乱），缺少层级归属
- 节点耗时不可见，用户无法区分"正常运行慢"与"卡死"

前置 delta `fix-pipeline-banner-and-eta` 已补齐 `node_start` 事件流与节点级计时，本 delta 在此基础上将管线 UI 重新设计为**分层时间轴**（方案 A，经讨论选定），直观呈现每个 agent 的执行状态、耗时与层级归属。

## What Changes

- **分层时间轴组件**：将现有 `PipelineCard` 的 6 阶段圆点进度条重构为可展开的分层树形时间轴：
  - 顶层：6 个 layer 节点（PREP / Layer I / Layer II / Trader / Risk / Fund），各显示状态图标（等待 ○ / 运行 ◐ / 完成 ●✓ / 失败 ✗）、层耗时
  - 第二层（可展开）：layer 内的子节点列表，各显示角色名、状态、节点耗时；当前运行节点显示已运行时长
  - Layer I 子节点为 4 个并行分析师（fundamental/technical/macro/sentiment），Layer II 为 bull_r1→bear_r1→bull_r2→bear_r2→research_manager，Layer IV 为 aggressive/neutral/conservative/risk_judge
- **修复 Layer I 分析师状态映射**：后端为 Layer I 的 Send 扇出 4 个并行分析师分别发 node_start/node_complete（节点 ID 区分），前端按各自事件驱动各卡片状态，并修复摘要文案错位
- **思考横幅归入层级**：当前活跃节点在时间轴内联显示实时思考摘要（截断的单行预览），点击展开完整 timeline；已完成节点的思考折叠到节点条目下
- **当前任务高亮**：时间轴自动滚动到当前运行节点并高亮，用户一眼定位"现在执行到哪个 agent"
- 保留"查看实时输出日志"折叠区与 ETA 显示（上一 delta 成果）

非目标：不改动后端图结构与节点编排；不改动报告渲染区；不做泳道图/甘特图等替代可视化；不处理辩论层并行化。

## Capabilities

### New Capabilities

（无新增 capability）

### Modified Capabilities

- `frontend`:
  - 修改 `Pipeline Progress Display`：6 阶段圆点改为分层时间轴结构，新增子节点列表、状态图标、层/节点耗时、自动滚动高亮等场景
  - 修改 `Pipeline Thinking Display`：思考横幅归入时间轴节点条目，当前节点内联实时摘要
  - 修改 Layer I 分析师卡片相关场景：按并行节点各自事件驱动状态，修复摘要错位

## Impact

**受影响代码**：

- 后端：
  - `src/finance_agent/graph.py` / `src/finance_agent/api.py` / `src/finance_agent/agent_factory.py`：Layer I 并行分析师节点事件需携带区分 4 个分析师的节点 ID（现状 4 分析师并行结果合并为单个 updates chunk，需在事件层拆分或用 sub-node 标识）
- 前端：
  - `frontend/src/App.tsx`：`PipelineCard` 重构为分层时间轴组件（或拆分为新组件 `PipelineTimeline.tsx`）
  - `frontend/src/types.ts` / `frontend/src/timeline.ts`：节点状态树模型
  - `frontend/src/TimelineRenderer.tsx`：节点条目内联渲染
- 测试：前端组件单测、E2E 管线进度断言更新、人工验证报告

**依赖**：前置 delta `fix-pipeline-banner-and-eta` 已落地（node_start 事件流、节点计时、ETA）。

**风险**：Layer I 并行事件的节点 ID 拆分涉及后端事件协议细化，需保持向后兼容；时间轴展开/折叠的默认状态需人工验证确定最佳默认值。
