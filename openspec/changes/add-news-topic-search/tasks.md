# Tasks: add-news-topic-search

- [ ] 1. 失败测试先行：detect_search_topic 词表判别（新闻意图命中/未命中/显式优先）
- [ ] 2. 失败测试：tavily_search 按 topic 透传 TavilyClient（news/general/显式覆盖），mock 层验证
- [ ] 3. 实现：web_search.py 加 detect_search_topic + topic 可选参数与自动判别，测试转绿
- [ ] 4. 全量回归（pytest -m "not live" + ruff + mypy）
- [ ] 5. 真实链路验证：新闻 query 经 news 通道的实际召回对比 general（人工抽查）
