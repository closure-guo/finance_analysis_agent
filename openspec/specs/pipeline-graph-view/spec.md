# pipeline-graph-view Specification

## Purpose
TBD - created by archiving change add-pipeline-graph-view. Update Purpose after archive.
## Requirements
### Requirement: 管线图视图与列表切换

深度分析管线的进度展示 SHALL 提供「图 / 列表」两种视图：图视图以 DAG 节点图呈现管线拓扑与实时状态，列表视图为现有层级时间轴。用户的视图选择 SHALL 持久化到 localStorage 并在下次进入时生效；视口宽度 <768px 时 SHALL 仅提供列表视图。

#### Scenario: 默认展示与切换

- GIVEN 深度分析正在运行且视口宽度 ≥768px
- WHEN 用户在管线区首次查看进度
- THEN 系统 SHALL 默认展示图视图
- AND 用户点击「列表」SHALL 切换到现有层级时间轴且管线状态流转不中断

#### Scenario: 视图偏好持久化

- GIVEN 用户切换到「列表」视图
- WHEN 用户刷新页面或进入下一次深度分析
- THEN 管线区 SHALL 直接展示列表视图（读取 localStorage）

#### Scenario: 窄屏降级

- GIVEN 视口宽度 <768px
- WHEN 用户查看管线进度
- THEN 系统 SHALL 仅展示列表视图且不渲染图/列表切换控件

### Requirement: 图视图节点状态呈现

图视图 SHALL 按 DAG 拓扑渲染六层管线节点（PREP → 四分析师并行 → 多空辩论 → Trader → 风控辩论 → FM），节点 SHALL 展示实时状态（pending/running/completed/failed）与耗时；节点状态流转 SHALL 与列表视图来自同一状态树（pipelineTree），两视图 SHALL 一致。

#### Scenario: 实时状态着色

- GIVEN 深度分析运行中
- WHEN 某节点开始执行
- THEN 图上该节点 SHALL 显示运行中样式（蓝色脉冲）
- AND 节点完成时 SHALL 转为完成样式（绿色）并显示耗时

#### Scenario: 并行层呈现

- GIVEN 管线进入 Layer I
- WHEN 四个分析师节点并行执行
- THEN 图上四个节点 SHALL 以同级并行布局呈现且状态独立流转

### Requirement: 退回循环可视化

图视图 SHALL 常驻渲染 FM→Trader 条件回边（虚线低透明度）；当 FM 退回导致节点重跑时，回边 SHALL 转为高亮动画样式，被重跑的节点 SHALL 显示迭代徽标 ×N（N 为该节点累计执行次数，N≥2 时显示）。

#### Scenario: FM 退回触发回边高亮

- GIVEN 深度分析运行中且 FM 对交易方案发出退回
- WHEN Trader 与 FM 节点重跑
- THEN FM→Trader 回边 SHALL 转为高亮动画
- AND Trader 与 FM 节点 SHALL 显示迭代徽标 ×2
- AND 节点状态 SHALL 沿用单调状态机语义（与列表视图一致）

### Requirement: 节点详情卡片

用户点击图上节点时，系统 SHALL 展示悬浮卡片，内容包含节点状态、耗时与一句话摘要（取自节点 output.summary）；卡片 SHALL 提供「查看详情」操作，点击后 SHALL 切换到列表视图并展开对应节点的详情。

#### Scenario: 查看节点摘要并跳列表

- GIVEN 图视图中某分析师节点已完成且含 output.summary
- WHEN 用户点击该节点
- THEN 系统 SHALL 展示悬浮卡片显示状态/耗时/摘要
- AND 用户点击「查看详情」后 SHALL 切换到列表视图且该节点为展开状态

#### Scenario: 运行中节点点击

- GIVEN 某节点正在运行
- WHEN 用户点击该节点
- THEN 悬浮卡片 SHALL 展示「运行中」状态与已运行时长，不含摘要

### Requirement: 图视图缩放控制

图视图 SHALL 在画布右下角常驻提供「放大 / 缩小 / 重置」三个控件：放大按 ×1.2 步进、缩小按 1/1.2 步进、重置恢复到适配视图总览（与初始 fitView 语义一致：padding 0.15、maxZoom 1）。缩放范围 SHALL 钳制在既有边界（minZoom 0.4 / maxZoom 1.5）内，到达边界时对应按钮 SHALL 呈禁用态；双击放大等既有交互 SHALL 不变。

#### Scenario: 缩小与放大步进

- GIVEN 深度分析运行中且图视图已渲染，当前缩放位于边界内
- WHEN 用户点击「缩小」
- THEN 画布缩放 SHALL 变为原值的 1/1.2（步进）
- AND 用户点击「放大」后缩放 SHALL 恢复（×1.2 步进）

#### Scenario: 重置回总览

- GIVEN 用户已通过放大/缩小或双击改变了视图缩放与平移
- WHEN 用户点击「重置」
- THEN 画布 SHALL 恢复为适配视图的总览状态（全部节点可见）

#### Scenario: 缩放边界禁用

- GIVEN 用户连续放大至 maxZoom（1.5）
- THEN 「放大」按钮 SHALL 禁用
- WHEN 用户连续缩小至 minZoom（0.4）
- THEN 「缩小」按钮 SHALL 禁用

