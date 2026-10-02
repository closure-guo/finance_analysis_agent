# Tasks: add-index-performance-compare

## 1. 指数收盘存储与日批落库

- [x] 1.1 `INDEX_COMPARE_UNIVERSE` 常量落位(5 指数 code+中文名),`index_closes` 建表迁移 + upsert/查询函数(TDD:幂等重跑、按窗口读取)
- [x] 1.2 盯市日批顺带拉取指数收盘并落库(TDD:全部成功落库、单指数失败隔离不进 errors 汇总、行情全失败盯市仍成功)
- [x] 1.3 历史回填脚本(近 400 自然日,串行+退避,幂等可重跑)+ 对生产库执行回填并抽验行数

## 2. index-compare 读数 API

- [x] 2.1 区间收益计算模块:组合窗口截断、指数基期向过去回退、缺数 null 语义(TDD:正常读数/基期回退/全缺/净值不足/跨度截断五场景)
- [x] 2.2 `GET /api/v1/track-record/index-compare` 端点接入(含 as_of/disclaimer,与 equity-curve 同语义)+ 集成测试

## 3. 前端对比卡片

- [x] 3.1 响应类型定义 + 对比卡片组件(N/M 摘要、组合条置顶、收益降序、绿↑红↓灰显、起算日标注)
- [x] 3.2 战绩页接入:卡片应用 fa_track_prefs.timeSpan 跨度偏好(进页读取一次,与净值图同源)、空态渲染
- [x] 3.3 前端单测(渲染/联动/空态)+ E2E spec(正常渲染与跨度切换,真实 stub 后端)

## 4. 验证收口

- [x] 4.1 后端全量测试 + ruff + mypy 通过;前端 npm test 通过
- [x] 4.2 E2E 门禁全绿(cd e2e && npx playwright test)
- [x] 4.3 人工验证报告落 tests/validation/(卡片视觉、真实指数读数抽验与行情源核对)
