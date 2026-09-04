# Tasks: add-hallucination-rate-metric

## 1. claim 抽取

- [ ] 1.1 失败测试先行：抽取结构与 contradicted/unverifiable 判定
- [ ] 1.2 claim 抽取（评测链路 LLM 调用，不进生产链路）

## 2. 校验与指标

- [ ] 2.1 证据源对接（akshare 封装 + 检索内容）
- [ ] 2.2 hallucination_rate 计算（容差配置化）

## 3. 门禁

- [ ] 3.1 上限阈值纳入门禁 + nightly 趋势
- [ ] 3.2 contradicted claim 清单输出

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 真实报告样本端到端校验
