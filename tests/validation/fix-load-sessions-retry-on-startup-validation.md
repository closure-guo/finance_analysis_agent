# 验证报告：首次加载历史会话自动重试修复

## 问题背景

用户反馈：agent 启动后无法看到历史会话记录，需要手动刷新才能看到。

## 根因

双层失效：
1. **基础设施层**：`docker-compose.yml` 中前端 `depends_on: backend: condition: service_started`，只等后端容器进程启动，不等 uvicorn 监听端口。后端启动需要 ~4 秒（Python 加载 + `build_5layer_graph` + `init_db` + lifespan），期间前端已就绪并调用 `/api/sessions`，nginx 返回 502。
2. **前端容错层**：`App.tsx` 中 `loadSessions` 首次 fetch 失败后只 `console.error`，不重试，`sessions` state 保持空数组 `[]`。`useEffect` 只执行一次，不会再次调用 `loadSessions`。

用户手动刷新时后端已就绪，`loadSessions` 成功，所以能看到历史会话。

## 修复方案

双层防御：

### 1. 前端容错（`App.tsx`）

`loadSessions` 返回 `Promise<boolean>` 标识成功/失败。`useEffect` 初始化时退避重试（500ms, 1s, 2s, 4s, 8s, 16s，最多 6 次），覆盖后端 ~4 秒启动窗口。其他调用点（`handleStreamTerminal`、`session_created` 事件等）保持原行为（单次请求，忽略返回值）。

```typescript
const loadSessions = useCallback(async (): Promise<boolean> => {
  try {
    const resp = await fetch('/api/sessions')
    if (!resp.ok) return false
    const data = await resp.json()
    setSessions(data.sessions || [])
    return true
  } catch (e) {
    console.error('Failed to load sessions:', e)
    return false
  }
}, [])

useEffect(() => {
  let cancelled = false
  let retryCount = 0
  const maxRetries = 6

  const loadWithRetry = async () => {
    const ok = await loadSessions()
    if (cancelled) return
    if (!ok && retryCount < maxRetries) {
      const delay = 500 * Math.pow(2, retryCount)
      retryCount++
      setTimeout(loadWithRetry, delay)
    }
  }

  loadWithRetry()
  return () => { cancelled = true }
}, [loadSessions])
```

### 2. 基础设施 healthcheck（`docker-compose.yml`）

后端添加 healthcheck（`/api/sessions` 探活），前端 `depends_on` 改为 `condition: service_healthy`。docker compose 启动时前端会等后端 healthcheck 通过才启动，从源头避免首次请求失败。

```yaml
backend:
  healthcheck:
    test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/sessions', timeout=3).read()\""]
    interval: 3s
    timeout: 5s
    retries: 15
    start_period: 5s

frontend:
  depends_on:
    backend:
      condition: service_healthy  # 原为 service_started
```

## 验证证据

### 1. 专项测试（TDD 红绿）

**测试文件**：`frontend/src/test/load-sessions-retry.test.tsx`

模拟首次 `/api/sessions` 返回 502（后端未就绪），第二次返回 200（含 2 个历史会话）。验证重试后历史会话显示在侧边栏。

- **修复前**：首次 502 -> catch -> sessions 空数组 -> 不重试 -> 找不到"贵州茅台分析" -- 测试失败
- **修复后**：首次 502 -> catch -> 退避重试 -> 第二次 200 -> sessions 更新 -> 显示"贵州茅台分析" -- 测试通过

### 2. 全量前端测试

```
npm test
Test Files  16 passed (16)
     Tests  139 passed (139)
```

含新增的 load-sessions-retry 测试，全部通过，无副作用。

### 3. Docker 重建验证

`docker compose up -d --build frontend backend` 输出关键序列：

```
Container finance-agent-backend-1 Started
Container finance-agent-backend-1 Waiting
Container finance-agent-backend-1 Healthy    <- healthcheck 通过
Container finance-agent-frontend-1 Starting   <- 后端就绪后前端才启动
Container finance-agent-frontend-1 Started
```

修复前：前端不等待后端 healthcheck，直接启动，首次 `/api/sessions` 失败。
修复后：前端等后端 Healthy 后才启动，从源头避免首次请求失败。

### 4. 后端启动耗时实测

```
后端重启时刻: 08/02/2026 22:52:10
[0.19s] HTTP: 000   <- 连接失败
[0.75s] HTTP: 000
[1.28s] HTTP: 000
[1.82s] HTTP: 000
[2.36s] HTTP: 000
[2.90s] HTTP: 000
[3.45s] HTTP: 000
[4.07s] HTTP: 200   <- 后端就绪
```

后端需要 ~4 秒才就绪。前端退避重试序列（500ms, 1s, 2s, 4s）在 4.5 秒内必然命中后端就绪窗口。

## 影响范围

- **修改文件**：
  - `frontend/src/App.tsx`（loadSessions 返回 boolean + useEffect 退避重试）
  - `docker-compose.yml`（后端 healthcheck + 前端 depends_on 改为 service_healthy）
- **新增测试**：`frontend/src/test/load-sessions-retry.test.tsx`
- **无后端代码改动**
- **无 OpenSpec delta**（属于"小改动"，配置 + 前端容错，不动 openspec）

## 验证日期

2026-08-02
