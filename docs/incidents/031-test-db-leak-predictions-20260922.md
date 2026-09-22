# 031: 测试泄漏生产库——假决策写进 predictions 66 行，战绩数据基础失真（2026-09-22）

## 症状

`data/sessions.db` → `predictions` 表自 2026-09-07 起断续出现同一形态的伪造行：
600519（贵州茅台）`long`、confidence 恒 0.7、`langfuse_trace_id` 全空、
`fund_manager_decision`=None、`status='unresolvable'`、
`rationale_snapshot` 恒为 `{"action": "buy", "fund_manager_decision": null, "fund_manager_decision_reasoning": null}`
（`snapshot_hash` 指纹恒为 `ffc27e76…`）。至 2026-09-22 累计 **66 行**。

**发现渠道**：决策层「全 watch」取证（#134）附带发现 → #133 立项溯源。

## 根因

`tests/test_deep_trace_root.py::TestRunGraphStreamingEvalFullData::test_metadata_has_full_eval_fields`
（约 334-353 行）：

1. patch 掉 `finance_agent.api.graph`（假图 `_fake_graph_full_eval`，其 risk_judge chunk 写死
   `{"action": "buy", "confidence": 0.7}`），但调用的是**真实** `api._run_graph_streaming(...)`
   ——图是假的，**落库挂点是真的**；
2. 该测试未隔离任何数据库路径（既没有 SESSIONS_DB_PATH，也没有 patch
   `session_store._DB_PATH` / `model._default_db_path`）→ `_persist_decision_log`
   （api.py:1141 → ingest.py:53）写入开发库 `data/sessions.db`。

**每次跑一次全量套件 = 写一行。** 9/7–9/9 的高频批量（14+9+11 行/日）对应开发期反复跑套件；
9/16 之后零星行对应各次单跑/子集跑。

### 为什么长期未被发现

- 落库是**旁路**（`ingest` 内部吞异常、失败不阻断测试）→ 测试全绿与污染并存；
- 既有隔离是**按测试自觉**的（`isolated_db` / `monkeypatch _DB_PATH` 模式，
  incident 013 已立「DB 环境变量隔离」原则）——默认路径仍是开发库，
  **漏一个测试就全漏**；`REPORTS_DIR` 当年用 conftest 全局 autouse fixture 修过同类问题
  （live E2E 往 reports/ 堆垃圾文件），DB 侧没有对应全局隔离。

## 影响面

- **战绩/校准数据基础失真**：`agent_metrics_daily`（win_rate/sharpe/回撤）与 `equity_curve`
  按含污染行的口径计算；任何以 predictions 为源的分析（含取证①）需人工分段清洗；
- **不涉及生产链路**：生产落库路径本身正确，缺的是测试环境隔离。

## 判定

**真问题（测试设施泄漏，非模型/管线缺陷）**。取证① 曾据此把 09-07 起的行判为「evals 跑批污染」——
错误归因，实为测试泄漏；已同步更正取证报告的对应表述。

## 写入面完整枚举（插桩 11 笔写入尝试）

| 调用点 | 性质 |
|---|---|
| `tests/test_deep_trace_root.py:349`（+同族 3 例经 `_run_graph_streaming`） | **真泄漏**（无任何 DB 隔离）→ 66 行 |
| `tests/outcome/test_decision_logging.py`（3 例直调 `_persist_decision_log`） | 已自行 patch `model._default_db_path`，写入 tmp 库（非泄漏） |
| `tests/outcome/test_track_record_ingest.py`（3 例） | 同上（非泄漏） |
| `tests/outcome/test_track_record_ingest_shared.py`（4 例） | 同上（非泄漏） |

即：**隔离是「按测试自觉」模式，漏一个测试就全漏**——本 incident 的 4 个写入面中
3 个自觉隔离、1 个漏，泄漏行全部来自漏的那个。

## 修复（已实施）

1. **全局默认隔离**（`tests/conftest.py::_isolate_runtime_dbs`，函数级 autouse，**live 豁免**）：
   ① `SESSIONS_DB_PATH` → 临时目录（predictions 侧 `model._default_db_path()` 调用时读取）；
   ② `session_store._DB_PATH` → 同一临时库（模块导入期冻结的常量，直接改模块属性）；
   ③ 隔离库**自带 schema**（`session_store.init_db()` + `init_predictions()`）——非 live
   测试会经真实挂点写两张表，空文件会 `no such table`（首版漏此步，组合跑复现后补齐）。
   **live 豁免**：live 是手动发起的真实测量（`test_hallucination_live.py` 从开发库取样
   历史报告），按设计读开发库；首版未豁免曾令该 live 测试红（空库无 sessions 表），
   已按 REPORTS_DIR 先例改为豁免。个别非 live 测试自行 monkeypatch 时其 patch 覆盖默认值。
2. **回归护栏**（`tests/test_db_isolation.py`）：断言非 live 测试期间两处路径均不指向
   `data/sessions.db`（红→绿，先红证明当时默认路径确实未隔离）。
3. **存量清理**：按 `snapshot_hash` 指纹精确删除 66 行（备份 `data/sessions.db.bak-20260922`，
   已补 `.gitignore` 规则）；删前核验无 `daily_marks` 引用。清理后 51 行 = 30 回填 + 21
   真实运行（trace 均为真实 Langfuse id，零测试痕迹）。

## 证据链

- SQLite 审计触发器（`_pred_audit`）捕获全量套件运行中的写入时间点；
- Python 栈插桩（临时 `pred_audit_plugin.py` 包装 `ingest.insert_prediction`）捕获完整调用栈：
  `tests/test_deep_trace_root.py:349` → `api.py:1141` → `ingest.py:53`；
- 单元复现：单跑 `tests/test_deep_trace_root.py` 曾必增一行（predictions 114→115 / 116→117）；
  修复后单跑与全量均零新增（117→117；清理后 51 行稳定）。

## 教训

- **测试隔离必须「默认安全」**：默认路径即隔离（conftest 全局兜底），不能靠每个测试自觉；
- **旁路挂点要在测试环境默认关闭或指向临时库**——「失败不阻断」的设计会把污染藏得最久；
- 顺带更正：取证① 报告的「09-07 起 evals 跑批污染」表述应改为「测试泄漏」（evals 侧
  `pilot_runner` 离线 `graph.invoke` 不落库，已排除）。
