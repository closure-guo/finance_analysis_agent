# Tasks: add-peer-comparison

- [ ] 「对比 600519 和 000858」类请求触发单条完整管线，主标的报告基本面章节含同业对比段（对照表 + 相对估值结论 + 口径标注）
- [ ] `run_deep_analysis` 暴露 `peer_codes` 参数：LLM 经 search_stock 解析传入；无效代码剔除并告知；超 3 只截断并告知；显式传参优先于请求闭包
- [ ] `fetch_peer_data` 扩展字段实源验证通过，字段组级降级符合 spec（含财务组全失败仅估值组场景、单标的跳过场景）
- [ ] 同业指标格式化器注入基本面分析师 context（Issue #4 关闭）；无 peer 请求回归行为与现状一致
- [ ] prompts（deep_mode + 基本面分析师模板）修改已 deploy：`deploy_prompts.py` 执行且指纹一致（production == 本地）
- [ ] 人工验证报告落 `tests/validation/`：对比段数值可溯源至注入材料、降级缺失声明如实、无明显幻觉
