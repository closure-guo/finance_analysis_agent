# Incident 016: litellm 流式 logging 线程在 Windows 死锁（跑批挂死）

**日期**: 2026-08-16
**环境**: Windows 10 (26100) / Python 3.14.5 / litellm 1.85.1
**影响**: 本地跑批（evals baseline）及任何长流式 LLM 会话可能挂死；进程无法退出
**状态**: 已修复（`litellm.disable_streaming_logging = True` 双入口防护）

## 现象

- baseline-v2 跑批（16 行）启动 90 分钟无产出：CPU 时间冻结（173s 不增长）、无外部
  ESTABLISHED 连接、stdout 0 字节
- 进程名下出现一堆 `127.0.0.1:<随机端口>` LISTENING（7+ 个，Python 不应监听这些）
- 强杀后重跑复现：row 0 结束后线程数飙至 **105**，`ALL DONE` 打印后进程永不退出

## 根因（py-spy 三次 dump 铁证）

```
litellm 流式路径: 每个 chunk → executor.submit(run_success_logging_and_cache_storage)
                                  （全局 ThreadPoolExecutor(max_workers=100)）
  └ worker 内 asyncio.run() → 新建 ProactorEventLoop
      └ _make_self_pipe → Windows _fallback_socketpair
          （bind 127.0.0.1 随机端口 + connect + accept 模拟 socketpair）
          └ 多线程并发竞态 → accept() 永久阻塞
              → 线程卡死 + 泄漏一个孤儿监听端口（= 现象中的异常 LISTENING）
```

复现时 dump：**100/100 worker 全部卡死在 `_fallback_socketpair` 的 `accept()`**。
主线程栈：`_python_exit`（解释器退出钩子）→ `join` 卡死线程 → 进程永不退出
（此即此前「42 分钟 exit hang」incident 的同一根因——当时只在退出阶段发生）。

运行中挂死（90 分钟那次）为概率性同源故障：row 1 卡在风控辩论 → risk_judge
之间，节点线程的 LLM 流式调用被同一 logging 线程池全灭拖死。

## 为什么会全灭

一行 deep 管线 ≈ 15+ 次 LLM 调用 × 每次 ~150 chunks = 数千次 executor.submit；
LangGraph 并行节点（4 分析师同时流式）令多个 worker 同时 `asyncio.run()` 建 loop，
socketpair 竞态窗口打开。裸 litellm 调用（低并发）不复现——`tests/scripts/
repro_litellm_stream_deadlock.py` 30 次调用线程稳定 16。

## 修复

项目 Langfuse 观测走自研 SDK（`start_as_current_observation`），**未注册任何
litellm callback**，logging 链纯开销零收益 → 启用 litellm 官方开关短路两条路径
（`streaming_handler.py:1787` return / `:1866` 不 submit）：

- `src/finance_agent/llm.py`（管线主路径）
- `src/finance_agent/harness/litellm_client.py`（harness/quick 独立导入路径）

守护测试：`tests/test_litellm_stream_deadlock_guard.py`（含 subprocess 用例锁
harness 独立导入路径）。

## 验证

- 复现脚本 `tests/scripts/repro_baseline_deadlock.py`（与跑批同路径跑前 2 行）：
  修复前 threads=105 + ALL DONE 后挂死需 taskkill；修复后 threads=6 稳定、
  **EXIT_CODE=0 正常退出**
- 全量 `pytest`: 875 passed（5 个 @live 失败为方舟端点 404 的环境性失败，与修复无关）

## 遗留

- 跑批行失败（JSONDecodeError 炸整行）为独立 bug：方舟 GLM-5.2 输出空 content /
  截断 / trailing comma，分析师层有降级、下游节点无降级 — 另案排查
- 升级 litellm 后可尝试移除本开关（关注上游对 Windows streaming logging 的修复）
