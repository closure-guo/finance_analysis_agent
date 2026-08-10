## ADDED Requirements

### Requirement: StreamStore 单一事实源

系统 SHALL 提供独立的 `StreamStore` 类作为前端流状态的唯一写入者和单一事实源，替代现有 App 组件持有的三份拷贝（React state、ref 镜像、手写注册表）。StreamStore 维护 `Map<sessionId, SessionStreamState>`，每个会话一份独立的 `SessionStreamState`，包含 `phase`、`messages`、`lastSeq`、`error` 字段。

#### Scenario: 新会话初始化状态

- **GIVEN** 用户发起新分析或快速对话
- **WHEN** `submit()` 被调用
- **THEN** StreamStore 为该 sessionId 创建 `SessionStreamState`，`phase='connecting'`，`messages` 包含用户消息
- **AND** 组件通过 `useSessionStream(sessionId)` 订阅到该状态

#### Scenario: 无会话时返回共享 IDLE 常量

- **GIVEN** `sessionId` 为 null
- **WHEN** `useSessionStream(null)` 被调用
- **THEN** 返回共享的 `IDLE_STATE` 常量（引用稳定），不创建新对象

### Requirement: 事件按 sessionId 分流写入

系统 SHALL 将 SSE 事件按 `sessionId` 写入对应 `SessionStreamState`，而非全局判断"是否当前视图"。迟到的事件写进它该去的会话，天然不会污染当前视图。

#### Scenario: 双会话并发流各自独立

- **GIVEN** 会话 A 和会话 B 同时有活跃流
- **WHEN** 会话 A 的事件到达
- **THEN** 事件仅写入会话 A 的 `SessionStreamState`
- **AND** 会话 B 的 `SessionStreamState` 不受影响

#### Scenario: 切出后迟到事件不污染当前视图

- **GIVEN** 用户从会话 A 切到会话 B
- **WHEN** 会话 A 的迟到事件到达（在途 SSE 回调）
- **THEN** 事件写入会话 A 的 `SessionStreamState`
- **AND** 当前视图（会话 B）的渲染不受影响

### Requirement: seq 守门与去重

系统 SHALL 在 `applyEvent` 中对事件实施 seq 守门：`event.seq <= lastSeq` 的过期事件被丢弃；`seq > lastSeq + 1` 的空洞事件触发显式 resync 而非静默跳过。

#### Scenario: 过期事件丢弃

- **GIVEN** 会话 A 的 `lastSeq = 5`
- **WHEN** 收到 `seq = 3` 的事件
- **THEN** 事件被丢弃，状态不变化

#### Scenario: seq 空洞触发 resync

- **GIVEN** 会话 A 的 `lastSeq = 5`
- **WHEN** 收到 `seq = 8` 的事件
- **THEN** 触发一次 `resume(after_seq=5)` 补齐缺失事件
- **AND** 补齐失败时降级为刷新会话详情

### Requirement: 单读取器结构性保证

系统 SHALL 保证同一时刻只有一个活跃 SSE reader。`pump` 开始前，若 `activeReader` 存在且属于其他会话，先 abort 并等待其退出。

#### Scenario: 切换会话时 abort 旧 reader

- **GIVEN** 会话 A 有活跃 reader
- **WHEN** 用户切换到会话 B
- **THEN** 会话 A 的 reader 被 abort
- **AND** 会话 B 的新 reader 启动前确认旧 reader 已退出

### Requirement: 不可变更新与引用稳定快照

系统 SHALL 通过 `reduce(state, event)` 纯函数产生不可变更新，`getSnapshot` 返回引用稳定的快照对象。`useSyncExternalStore` 的正确性依赖这一点。

#### Scenario: 相同事件不重复触发渲染

- **GIVEN** 某会话的 `SessionStreamState` 已渲染
- **WHEN** 同一事件再次到达（重复触发）
- **THEN** `reduce` 返回新对象但内容相同，`getSnapshot` 返回引用稳定的快照
- **AND** React 不触发重渲染

### Requirement: 会话切换协议原子化

系统 SHALL 将 `switchSession(id)` 实现为 store 内一次同步调用完成，外部无法插入。切换期间到达的事件进入目标会话自己的 state，通过 seq 自然排序。

#### Scenario: 切换会话不中断后台任务

- **GIVEN** 会话 A 的生成任务正在运行
- **WHEN** 用户切换到会话 B
- **THEN** 会话 A 的后台任务继续运行
- **AND** 仅断开本地订阅连接，不调用后端取消

#### Scenario: 切回运行中会话并续传

- **GIVEN** 用户从会话 A 切出，期间任务继续产出事件
- **WHEN** 用户再次点击会话 A
- **THEN** 加载会话快照后，经 `GET /api/sessions/A/stream?after_seq={lastSeq}` 重连事件流
- **AND** 重放事件与实时事件经同一 `reduce` 消费，UI 幂等重建

### Requirement: 页面刷新恢复

系统 SHALL 在页面刷新后从 localStorage 读出 `sessionId`，经 `switchSession` 恢复会话状态。`switchSession` 时以后端 `SessionDetail.status` 为准：interrupted/failed 直接定型，不发起 resume。

#### Scenario: 刷新后恢复运行中会话

- **GIVEN** 页面刷新前会话 A 正在流式输出
- **WHEN** 页面重新加载
- **THEN** 从 localStorage 读出 sessionId，调用 `switchSession`
- **AND** 经 `GET /api/sessions/A/stream?after_seq=` 恢复事件流
- **AND** 输出内容从断点继续增长，不重复、不遗漏

#### Scenario: 刷新后恢复已中断会话

- **GIVEN** 页面刷新前会话 A 被中断（status=interrupted）
- **WHEN** 页面重新加载
- **THEN** 展示已落库的半截回复及"输出已中断，可追问继续"标记
- **AND** 不显示无限转圈的 streaming 状态
