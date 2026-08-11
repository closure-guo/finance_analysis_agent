---
title: 前端流状态架构 — StreamStore 单一事实源
config:
  theme: base
  themeVariables:
    fontFamily: "system-ui, -apple-system, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "15px"
---
flowchart LR
    subgraph L1["React 组件层"]
        direction TB
        chatInput["ChatInput / ModeSwitcher<br/>输入 · 模式切换 · 发送"]
        appTsx["App.tsx 主组件<br/>selectSession · 轮询 effect<br/>deriveAppState"]
        useStream["useSessionStream<br/>useSyncExternalStore 订阅"]
        view["视图渲染<br/>MessageRenderer<br/>PipelineTimeline · ReportCard"]
    end

```mermaid
subgraph L2["StreamStore 状态层（单一事实源）"]
    direction TB
    state["状态 SessionStreamState<br/>phase · messages<br/>lastSeq · origin"]
    reduce["reduce 纯函数<br/>thinking_token · chat_token<br/>pipeline 事件归约"]
    commands["命令方法<br/>submit · resume · switchSession<br/>rebuildSession · updatePipelineSnapshot"]
    subscribe["订阅接口<br/>subscribe · getSnapshot · emit"]
end

subgraph L3["数据访问 / SSE 泵"]
    direction TB
    pump["pump<br/>读 SSE 流 → applyEvent → reduce"]
    submit["提交<br/>POST /api/analyze · /api/chat"]
    detail["会话详情<br/>GET /api/sessions/:id"]
    resume["续传重放<br/>GET .../stream?after_seq=0"]
end

subgraph L4["后端服务"]
    direction TB
    backend["分析 / 聊天服务 (backend)"]
    snapshot["会话详情 + 快照<br/>pipeline_snapshot · chat_history"]
    journal[("session_events journal<br/>全量事件日志")]
    sseStream["SSE 流<br/>实时推送 + after_seq 重放"]
end

%% ===== 实时流式主链路（实线） =====
chatInput -->|发起| submit
submit -->|POST| backend
backend -->|写入| journal
journal --> sseStream
sseStream -->|SSE 事件| pump
pump -->|applyEvent| reduce
reduce -->|归约写状态| state
state -->|emit| subscribe
subscribe -->|订阅| useStream
useStream -->|渲染| view
appTsx -->|命令| commands
commands --> state

%% ===== 刷新恢复（橙色虚线） =====
appTsx -.selectSession.-> detail
detail -.GET detail.-> snapshot
snapshot -.rebuild 回填.-> commands
commands -.resume(after_seq=0).-> resume
resume -.journal replay.-> sseStream

%% ===== 轮询兜底（紫色虚线） =====
appTsx -.轮询快照.-> detail

%% ===== 样式 =====
classDef react fill:#0891B2,stroke:none,color:#fff
classDef store fill:#E99151,stroke:none,color:#fff
classDef pump fill:#7C3AED,stroke:none,color:#fff
classDef backendNode fill:#64748B,stroke:none,color:#fff
classDef storage fill:#E99151,stroke:none,color:#fff

class chatInput,appTsx,useStream,view react
class state,reduce,commands,subscribe store
class pump,submit,detail,resume pump
class backend,snapshot,sseStream backendNode
class journal storage

%% 主链路实线加粗（索引 0-11）
linkStyle 0,1,4,5,6,7,8,9 stroke:#005D7B,stroke-width:3px
linkStyle 2,3,10,11 stroke:#94A3B8,stroke-width:2px
%% 刷新恢复橙色（索引 12-16）
linkStyle 12,13,14,15,16 stroke:#E99151,stroke-width:2px,stroke-dasharray:5 5
%% 轮询兜底紫色（索引 17）
linkStyle 17 stroke:#7C3AED,stroke-width:2px,stroke-dasharray:5 5
%% SSE 事件绿色（索引 4）
linkStyle 4 stroke:#4CA497,stroke-width:3px
```
