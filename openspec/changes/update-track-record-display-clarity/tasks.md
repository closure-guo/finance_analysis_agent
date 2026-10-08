# Tasks: update-track-record-display-clarity

## 1. 后端

- [ ] 1.1 `prediction_stats` / overview 新增 `legacy_open`（旧口径 open 计数），单测+集成测试覆盖（双计数独立、0 值语义）
- [ ] 1.2 `list_predictions` 行内注入 `latest_mark`（open 行最新盯市 {mark_date, cum_return, cum_excess}，批量窗口函数；无 marks → null），单测覆盖（有/无盯市、非 open 行 null、分页边界）
- [ ] 1.3 keyword 状态标签集合更新（+带内中性/回避/同日重复，「中性」状态词下线、方向词保留），过滤用例同步
- [ ] 1.4 `/api/test/seed` track_record 通道扩展 `marks` 造数（走生产 upsert 同路径），供 E2E 浮动收益场景

## 2. 前端

- [ ] 2.1 观点日志新增「窗口」列（T+N，展示列不排序）；副标题措辞修正（移除「20 日」硬编码）
- [ ] 2.2 open 行浮动收益：区间收益/基准超额列读 `latest_mark`（附盯市日期 title），无盯市「—」；「未结算」标注保留
- [ ] 2.3 同日重复折叠：consecutive (symbol, 建立日期) dup 行合并汇总行「同日重复 ×n」，点击展开/收起（当前页作用域，total 不变）
- [ ] 2.4 切片空态：settled=0 时切片区折叠为一行说明
- [ ] 2.5 术语：横幅/胜率卡/回避卡「已判定」→「已结算」；`predictionStatus.ts` resolved_neutral →「带内中性」；新建 `predictionDisplay.ts`（direction/resolution_rule 中文映射），详情页接入
- [ ] 2.6 前端单测：窗口列/浮动收益/折叠交互/空态折叠/术语/详情页映射（存量「中性」文本断言同步为「带内中性」）

## 3. 门禁与验证

- [ ] 3.1 E2E spec 覆盖：窗口列渲染、浮动收益（seed marks）、同日重复折叠/展开、切片空态、详情中文映射；scan.sh P0=0 + 审查通过（存量「中性」断言变更在 diff 中说明）
- [ ] 3.2 全量门禁：ruff / mypy 零新增、pytest 全绿、vitest 全绿、E2E 专属套件全绿；若 #256 已合并，验收含 1280px 无横向溢出
- [ ] 3.3 人工验证报告落 `tests/validation/`（真实数据抽查：四总数可对账、252 行可识别、拓荆组折叠、open 行浮动收益、术语/详情中文化）
