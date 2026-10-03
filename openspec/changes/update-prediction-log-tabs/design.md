# Design: update-prediction-log-tabs

## Context

后端 `GET /api/v1/track-record/predictions` 的 `status` 参数当前是精确匹配(`status = ?`),只能查单值状态;「已判定」是集合概念(resolved_win/loss/neutral、avoidance、unresolvable 六态),前端无法用一个参数表达。表区块无标题,缺省拉全部状态,与总览卡 open 口径(57)对不上。

## Goals / Non-Goals

**Goals:**
- 观点表获得标题「观点日志」与「当前持有 / 已判定 / 全部」三 tab,缺省当前持有
- tab 与总览卡口径自然对齐;切换走既有服务端过滤链路(分页正确)

**Non-Goals:**
- 不做按标的聚合持仓视图;不做各状态计数预取接口(徽标用当前响应 total)
- 不改判定语义/状态机本身

## Decisions

1. **后端 status 参数新增组值 `resolved`(唯一的后端改动)**:`status == "resolved"` 时 WHERE 追加 `status != 'open'`(覆盖六种已判定终态);其余取值保持精确匹配不变,向后兼容。归 track-record capability MODIFIED。
2. **tab → 请求映射**:当前持有 → `status=open`;已判定 → `status=resolved`;全部 → 不发 status 参数。
3. **缺省 tab = 当前持有**:与总览卡口径一致;「全部」保留审计视角。
4. **tab 切换 = setStatusFilter + setPage(1)**,经既有 predictionsUrl 依赖链自动重拉;徽标显示当前响应 total。
5. **E2E 数据策略**:专属套件库无 predictions 造数通道,新 spec 断言 tab 状态机(缺省 active=当前持有、点击切换后 active 态与 URL 参数变化);数据态断言(行数随 tab 变化)由单测覆盖(mock 层),空态文案不受 tab 影响作为兜底断言。

## Risks / Trade-offs

- `resolved` 组值与未来新增 open 态之外的状态语义耦合:新增非 open 状态自动归入"已判定",符合直觉,无需改代码
- 缺省视图从"全部"改为"当前持有"是行为变更:依赖"缺省看全部"的用户需多点一次「全部」——以总览卡口径一致性的收益换,spec 里写明
