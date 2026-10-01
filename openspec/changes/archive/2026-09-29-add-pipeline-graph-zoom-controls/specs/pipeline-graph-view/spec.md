# Delta for pipeline-graph-view

## ADDED Requirements

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
