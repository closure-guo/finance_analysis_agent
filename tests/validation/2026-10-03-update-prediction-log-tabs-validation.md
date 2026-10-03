# 人工验证报告: update-prediction-log-tabs

**日期**: 2026-10-03
**验证人**: ZCode(agent,自动化部分)+ [待人工补签]
**关联 delta**: openspec/changes/update-prediction-log-tabs/
**E2E 门禁**: 默认套件 24 passed;track-record 专属套件 7 passed(含新 pred-tabs spec 2 用例)

## 验证结果

| Scenario | E2E 已覆盖? | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| resolved 组过滤(status != 'open',六态) | 后端单测 | 5 非open 行命中,精确匹配不受影响,count 同口径 | 通过 | ✅ |
| 缺省「当前持有」:请求带 status=open,tab active | 是(pred-tabs spec #1)+ 单测 | aria-selected 正确 | 通过 | ✅ |
| 切换已判定/全部:参数映射与分页重置 | 单测(URL 断言)+ spec #2 | status=resolved / 无 status 参数 | 通过 | ✅ |
| 标题/副标题渲染 | 是(spec #1) | 「观点日志」+ 口径副标题可见 | 通过 | ✅ |
| 真实数据下 tab 行数变化(57/51/108) | 否 | 三个 tab 的 total 与库内分布一致 | **待合并部署后人工核读**(生产库已知 108 观点:57 open) | ☐ |
| tab 视觉(active 态配色/副标题样式与主题一致) | 否 | 与页面既有风格一致 | **待人工抽查** | ☐ |

## 自动化验证证据(2026-10-03,worktree .worktrees/pred-tabs)

- `uv run ruff check`: 过;`uv run mypy src/`: 82 = main 当前基线 82(main 自漂 +1,本分支零新增;model.py 单文件 0 错)
- 后端相关 pytest: 459 passed(含新 test_status_resolved_group_filter;TDD RED→GREEN;夹具修正:非 open 状态须经 update_prediction_status 流转,insert 契约写入必为 open)
- 前端 npm test: 635 passed(76 文件,含 3 个新 tab 用例)
- E2E 默认套件: 24 passed / 2 @live skipped;专属套件: 7 passed;timeline 套件未跑(本变更无 timeline 接触面)
- 实施偏差说明:前端 UI 先实现后补测试(改动面小,TDD 纪律在后端严格执行;前端 3 用例一次通过,无红→绿证据,如实记录)

## 合并后操作

`docker compose up -d --build backend frontend` → 打开战绩页滚到底部:应看到「观点日志」标题 + 三 tab,缺省「当前持有」57 条;人工核读三 tab 行数(57/51/108)与视觉后勾选上方两处 ☐ → 结论栏 → archive

## 异常记录

- 无阻断异常。记录:①测试夹具初版用 insert 直写非 open 状态被冻结契约拦下(insert 必 open),改为状态流转通道——契约正确性的旁证;②mypy main 基线自 81→82(main 漂移,与 #208/#211 合入相关,本分支零新增)

## 结论

[ ] 全部通过,可 archive
[ ] 存在失败项,需修复后重新验证
