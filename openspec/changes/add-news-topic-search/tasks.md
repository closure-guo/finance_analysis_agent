# Tasks: add-news-topic-search

- [x] 1. 失败测试先行：detect_search_topic 词表判别（新闻意图命中/未命中/显式优先）
- [x] 2. 失败测试：tavily_search 按 topic 透传 TavilyClient（news/general/显式覆盖），mock 层验证
- [x] 3. 实现：web_search.py 加 detect_search_topic + topic 可选参数与自动判别，测试转绿
- [x] 4. 全量回归（pytest -m "not live" + ruff + mypy）
- [x] 5. 真实链路验证：news 通道实测——具体 query「贵州茅台 600519 2026 业绩 新闻」8/8 中文财经新闻（界面/财新/每经），general 通道同 query 0 新闻（全导航页）；泛 query 中英混杂系 query 质量问题，react_agent 实际拼装的具体 query 不受影响（2026-09-12 agent 实测，owner 可复验）
