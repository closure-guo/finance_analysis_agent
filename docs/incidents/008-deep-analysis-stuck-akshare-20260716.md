# 008 - 深度分析交互卡顿（AKShare 数据拉取失败 + 无重试）

| 字段     | 值          |
| -------- | ----------- |
| 编号     | 008         |
| 日期     | 2026-07-16  |
| 标题     | 深度分析交互卡顿：管线 Layer I 长时间无进展 |
| 状态     | 部分修复    |
| 严重度   | 高（核心交互体验受损） |
| 发现方式 | 用户反馈"深度分析的交互有问题" + Playwright 诊断 |

## 现象

用户输入股票名（如"贵州茅台"）触发深度分析后，管线进度卡片在前 80 秒卡在 Layer I（4 个分析师"分析中..."），进度条不动，用户以为系统卡死。实际管线 258 秒后才完成。

## 诊断过程

按 diagnose skill 流程：
1. **Phase 1-2 复现**：Playwright 驱动前端输入"贵州茅台"，探测管线状态 200s，确认卡在 Layer I。
2. **直接抓 SSE 流**：`/api/analyze` 后端 SSE 40 事件 258s 完成，说明后端正常但慢。
3. **仪器化**：前端注入 `[DEBUG-DI]` console 日志，确认 `node_complete` 事件**被前端正确接收和处理**，进度条从 5%->18%->22.7% 正常更新。
4. **定位**：`technical_analyst` 节点输出"技术指标数据缺失"，后端日志显示 AKShare 行情/K线/行业数据拉取全部 `RemoteDisconnected`。

## 根因

### 主因：`_call_ak` 无重试，网络异常直接失败

[akshare_client.py](../../src/finance_agent/data/akshare_client.py) `_call_ak` 只捕获 `FuturesTimeoutError`，**不捕获 `ConnectionError`/`RemoteDisconnected`**。东方财富 API 对高频/无 UA 请求限频，首次连接被断开后无重试，直接返回 None，导致：
- K线数据缺失 -> 技术面分析输出"技术指标数据缺失"
- 行情数据缺失 -> 技术指标无法计算
- 行业归属缺失 -> 行业对比降级

### 次因：Langfuse Context 跨 async generator 边界

后端日志有 `ValueError: Token was created in a different Context` + `Calling end() on an ended span`。Langfuse OTel callback 在 async generator（`stream_agent_to_sse`）中跨 Context 边界，`GeneratorExit` 触发 detach 失败。属警告级，不阻断管线。

## 修复

### 修复 1：`_call_ak` 加重试 + 退避 + 全异常捕获（[akshare_client.py](../../src/finance_agent/data/akshare_client.py)）

```python
_AK_MAX_RETRIES = 3
_AK_RETRY_DELAY = 1.5

def _call_ak(func, *args, **kwargs):
    for attempt in range(1, _AK_MAX_RETRIES + 1):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=_AK_TIMEOUT)
            except FuturesTimeoutError:
                ...  # 重试
            except Exception as e:
                ...  # 捕获 RemoteDisconnected 等网络异常，重试
        if attempt < _AK_MAX_RETRIES:
            time.sleep(_AK_RETRY_DELAY * attempt)  # 线性退避
    return None
```

### 验证

修复后 `fetch_data` 输出从"已获取三大报表、宏观指标"（K线缺失）变为"已获取三大报表、**K线行情**、宏观指标"（K线成功），技术面分析数据完整。

## 未修复（记录）

- **管线总时长 258s**：Layer II 辩论 + Layer IV 风控多轮 LLM 串行调用，属架构性问题，需并行化重构（大改）。
- **Langfuse Context 警告**：OTel span 跨 async generator 边界，tracing 噪音，不阻断功能。
- **东方财富 API 限频**：连续请求触发 `RemoteDisconnected`，重试可缓解偶发，但高频仍会被封。长期需加请求频率限制 + 多数据源切换。

## 经验

- **外部 API 调用必须重试 + 退避**：`_call_ak` 原本只处理超时，忽略了 `ConnectionError`/`RemoteDisconnected` 这类更常见的网络异常，导致数据降级。
- **诊断要先确认"前端没收到" vs "后端没发"**：本次通过直接抓 SSE 流 + 前端 console 仪器化，排除了前端 bug，聚焦到后端数据层。
- **管线进度卡住≠管线挂了**：后端仍在运行（258s 完成），但数据缺失导致某些节点变慢，用户感知是"卡死"。
