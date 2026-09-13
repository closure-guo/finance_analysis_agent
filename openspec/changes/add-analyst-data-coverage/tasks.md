# Tasks: add-analyst-data-coverage

- [ ] 1. 失败测试先行：akshare_client 四个 fetcher（公告/研报/解禁/大宗，mock _call_ak；列名标准化、失败空列表、大宗按个股过滤）
- [ ] 2. fetcher 实现，测试转绿
- [ ] 3. 失败测试：fetch.py 装配（并行提交/state 键/缓存 TTL）+ state.py 新键
- [ ] 4. 装配实现，测试转绿
- [ ] 5. prompt 契约测试：fundamental_analyst.md 消费公告+研报+防锚定条款；sentiment_analyst.md 消费解禁/大宗
- [ ] 6. prompt 实现与 deploy_prompts
- [ ] 7. 失败测试：citation 回声匹配含四新源标题；实现转绿
- [ ] 8. 全量门禁（pytest -m "not live" + ruff + mypy 改动文件）
- [ ] 9. 真实链路验证（接口可用时跑 deep 分析人工核对四源落库与分析师引用）
