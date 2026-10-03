# Proposal: update-prediction-log-tabs

## Why

战绩页底部的观点表是全页信息密度最高的区块,却没有任何标题;「全部观点流水」与「当前组合(open)」两个概念混在一张无标题表里,总览卡「观点总数 57」与表内 108 条对不上,用户实测找不到、也分不清(2026-10-03 会话实测反馈)。后端 `status` 过滤参数已存在,纯前端即可修复。

## What Changes

- 观点表区块新增标题「观点日志」,副标题注明口径(每条=一次分析结论;open=仍在 20 日判定窗口内)
- 筛选栏新增三个状态 tab:**当前持有(open)/ 已判定(resolved_*/avoidance/unresolvable)/ 全部**(缺省=当前持有),切 tab 重置分页并按 status 服务端过滤(复用既有 status 参数,零后端改动)
- 总览「观点总数」卡与 tab 徽标口径对齐:总览卡保持 open 口径不变,tab 徽标显示各状态条数(随响应 total 更新)

## Capabilities

### New Capabilities
(无)

### Modified Capabilities
- `frontend`: 战绩页观点表新增区块标题与状态 tab(默认视图从「全部」改为「当前持有」)

## Impact

- 仅 `frontend/src/pages/trackRecord/TrackRecordPage.tsx` + 单测 + E2E(spec 断言 tab 切换与服务端过滤生效);后端零改动
- 交互类变更(前端 UI)→ 走 E2E 门禁(专属 track-record 套件)
