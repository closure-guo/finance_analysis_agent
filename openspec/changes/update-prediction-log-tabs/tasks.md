# Tasks: update-prediction-log-tabs

## 1. 后端 resolved 组值

- [x] 1.1 `_prediction_filters` 支持 status=resolved → `status != 'open'`(TDD:组过滤/精确匹配不变/total 一致)
## 2. 前端标题与 tab

- [x] 2.1 区块标题「观点日志」+ 副标题 + 三 tab(缺省当前持有,切换重置分页,active 标识,徽标 total)
- [x] 2.2 前端单测(缺省请求带 status=open/切换映射/重置分页)+ E2E spec(专属套件:tab 状态机与 active 标识)

## 3. 验证收口

- [x] 3.1 ruff + mypy 零新增 + 后端相关 pytest + 前端 npm test
- [x] 3.2 E2E 专属套件绿;人工验证报告落 tests/validation/
