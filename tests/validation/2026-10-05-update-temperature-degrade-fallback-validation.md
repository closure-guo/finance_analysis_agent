# 人工验证报告: update-temperature-degrade-fallback（部署后复测）

**日期**: 2026-10-05
**验证人**: ZCode（owner 委托执行）
**关联 delta**: openspec/changes/update-temperature-degrade-fallback/
**E2E 门禁**: 不适用（LLM 请求参数治理，非交互类变更）

## 部署核对

- backend 镜像 2026-10-05 06:43 重建（含 #216 合并后代码），容器 healthy
- 现行 provider 组合（2026-10-04 切点）：主链 openai/glm-5.3 @ bigmodel（thinking=enabled，reasoning_effort=low）；judge openai/kimi-for-coding @ Kimi Code（effort=none，suppress_temperature 契约）

## 复测（真实思考模型全链路）

- 触发：POST /api/analyze 600519 贵州茅台 综合深度分析（enable_web_search=true，全链路含 web search 工具调用）
- 结果：**completed**，10:54:41 发起、约 5 分钟完成，report_markdown 7646 字符，error=None
- 温度观测（docker logs 全窗口 grep temperature/降级）：
  - 仅出现「参数 temperature 被 adapter 白名单剔除(端点不支持)：model=openai/glm-5.3」前置剔除告警（请求不携带 temperature 出门）
  - **零 temperature 400 拒绝、零「拒绝后自动降级重试」事件**——修复语义（拒绝不触发降级重试）成立
  - kimi judge 链温度行为由 suppress_temperature 契约保证（#219 实测：思考档锁 1 / 无思考档锁 0.6）

## 备注

- delta 撰写时主链为 Kimi 思考模型；复测时点主链已切 bigmodel glm-5.3（metrics.md 2026-10-04 切点）。温度修复的全链路语义在现行组合下验证：主链温度白名单剔除 + judge 链温度抑制，两条路径均无拒绝-重试。

## 结论

- [x] 全部通过，可 archive
