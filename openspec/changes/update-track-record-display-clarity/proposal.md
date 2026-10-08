## Why

2026-10-08 生产实况 UX 审计确认战绩页存在系统性展示困惑：①同屏四个互不相等的总数（92/73/70/143）且无对账线索，「存量旧口径：无存量」与全部 tab 内 51 条 252 行并存的观感矛盾；②「基准超额」列整列为「—」而判定依据恰是超额（区间收益 -1.72% 却判「中性」无法自查）；③方向「中性」（观望）与状态「中性」（±2% 带内判定）同词不同义，「看空 中性」行读如矛盾修辞；④进行中行三列恒「—」（库内 daily_marks 106 行盯市数据未接）；⑤同日重复行无解释刷屏（10-02 拓荆 ×6 连屏）；⑥样本积累期切片区四维全「—」、未知桶主导，整页像故障；⑦详情页方向/判定规则显示英文原始值（short/superseded）。

## What Changes

- **判定窗口列**：观点日志新增「窗口」列（T+N，取行内 horizon_days），混合口径显式可见；可排序列清单同步更新
- **同日重复折叠**：「已判定」「全部」tab 中同 (symbol, 建立日期) 的 consecutive duplicate_of_day 行默认折叠为一行汇总（「同日重复 ×n」），点击展开；分页 total 不变，append-only 台账语义不变
- **进行中浮动收益**：观点日志 open 行的区间收益/基准超额列展示最新每日盯市读数（cum_return/cum_excess，源自 daily_marks），保留「未结算」标注与盯市日期提示；无盯市数据显示「—」
- **切片空态折叠**：settled=0 时切片指标区折叠为一行说明（首批观点结算后可用），不再渲染全「—」的四维表格
- **术语统一**：横幅与卡片「已判定 N 条」改「已结算 N 条」（win+loss 口径，与 tab 名「已判定」消歧）；状态 resolved_neutral 标签「中性」改「带内中性」（前端标签映射 + 后端 keyword 匹配同步）；详情页方向与判定规则中文映射（short→看空 / superseded→被新观点替代·提前结算 等）
- **口径披露补全**：overview 新增 legacy_open（旧口径进行中计数），披露行区分「旧口径已结算 0」与「另有 n 条旧口径进行中」；「当前持有」副标题移除「20 日」硬编码措辞（窗口列已使其准确）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `track-record`: 只读 API（overview 响应新增 legacy_open；keyword 状态中文标签集合更新）；战绩页面（窗口列、浮动收益、同日重复折叠、切片空态、术语、披露行）
- `frontend`: 观点日志标题与状态 tab（副标题措辞修正，口径说明移除 20 日硬编码）

## Impact

- 后端：`src/finance_agent/outcome/track_record/model.py`（overview 统计加 legacy_open；列表行注入最新盯市）、`src/finance_agent/api.py`（响应字段）
- 前端：`TrackRecordPage.tsx`（列/折叠/浮动收益/空态/文案）、`PredictionDetailPage.tsx`（中文映射）、`predictionStatus.ts`（标签）
- 测试：后端单测/集成、前端 vitest、E2E（折叠交互、浮动收益、窗口列；seed 通道需支持 daily_marks 造数）
- 不涉及：判定链路行为、统计口径分母、superseded 超额落库（另立 B 类裁决）、PR #256（结算入场价列）与 #260（当前观点区）已覆盖项
