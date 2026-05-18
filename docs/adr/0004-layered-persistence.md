# ADR-0004: Layered Persistence Strategy

## Status: Accepted

## Context

系统需要解决三个不同的持久化问题：
1. 执行中断了怎么办？（节点崩溃/用户关闭页面）
2. 同一只股票分析两次怎么办？（跨会话复用）
3. 研报怎么检索？（语义搜索）

三者解决不同问题，不能互相替代。

## Decision

采用四层持久化机制，各司其职：

| 机制 | 存储位置 | 用途 | 管理方式 |
|------|---------|------|---------|
| LangGraph State | 内存 | 节点间数据传递 | 自动 |
| LangGraph Checkpoint | SQLite (SqliteSaver) | 中断恢复，每个 node 执行完自动快照 | 自动 |
| SQLite Cache | SQLite (financial_metrics 表) | 跨会话数据复用，按 TTL 过期 | 手动（数据准备节点写） |
| Chroma | 本地文件 | 研报 embedding，RAG 语义检索 | 手动（搜索 Server 写） |

缓存 TTL 按数据类型差异化：
- 三大报表 / 预计算指标 / 衍生计算：到下个财报季
- 行情数据：到当日收盘（盘中不缓存）
- 券商研报：1 天
- 行业归属：30 天

数据准备状态机有四条执行路径：
- 热路径（FULL_HIT）：全部缓存命中 → 0 API 调用 → <0.5s
- 温路径（RAW_HIT）：原始数据有，指标没算 → 0 API 调用 → <1s
- 冷路径（PARTIAL_MISS）：部分缺失 → 2-3 次 API → ~3s
- 冰路径（FULL_MISS）：首次分析 → 5-8 次 API → ~6s

## Consequences

- Checkpoint 自动处理中断恢复，不需要手动同步 State 到数据库
- SQLite 缓存只存储更新频率低的数据，行情数据不缓存
- Chroma 只用于研报 RAG，不用作缓存
- 四条路径确保重复分析时响应速度极快
