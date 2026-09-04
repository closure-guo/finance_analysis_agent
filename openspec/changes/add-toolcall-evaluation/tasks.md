# Tasks: add-toolcall-evaluation

## 1. 轨迹提取

- [ ] 1.1 失败测试先行：轨迹提取与合法集合断言
- [ ] 1.2 从 Langfuse trace 提取工具调用序列

## 2. 评估维度

- [ ] 2.1 工具选择/参数合法性/调用效率/失败恢复四维评分
- [ ] 2.2 构造带工具调用预期的 quick 样本集（合法集合语义）

## 3. 门禁

- [ ] 3.1 回归阈值配置化 + @live nightly
- [ ] 3.2 退化样本清单输出

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 真实 quick trace 跑通端到端评估
