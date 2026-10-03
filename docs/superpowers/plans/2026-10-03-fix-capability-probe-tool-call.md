# fix-capability-probe-tool-call Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除能力探测「工具调用」假阴性（两级判定），配套「未测」态展示、warnings 人话化、test 端点结构化错误、前端前缀白名单回退。

**Architecture:** 后端 `run_live_probes` 的 tool_call 段改两级（auto+明确指令 → forced tool_choice 兜底），warnings 用机器码区分「端点拒绝」与「模型未调用」；`/api/llm-config/test` 捕获前缀错误返回结构化失败；前端 `llmConfig.ts` 加前缀白名单回退与两个纯函数（`formatProbeWarning`/`capabilityItemState`），`LlmConfigPane.tsx` 消费渲染三态矩阵与人话 warnings。

**Tech Stack:** FastAPI + litellm adapter（pytest + monkeypatch）、React 18 + TS + vitest。

## Global Constraints

- 所有命令在 worktree `D:/WorkSpace/finance_analysis_agent/.worktrees/fix-capability-probe-tool-call` 下执行
- 后端测试：`uv run pytest tests/llm/test_probes.py tests/test_api_llm_config.py -v`；Lint/类型：`uv run ruff check`、`uv run mypy`
- 前端测试：`cd frontend && npm test -- --run`（vitest）
- probe 缓存/响应契约不变：`/api/llm-config/test` 响应字段与 `CapabilityMatrix` 布尔结构不动
- commit 格式：`fix: [模块] 描述（fix-capability-probe-tool-call）`，单 commit 不混任务

---

### Task 1: 两级 tool_call 探测（probes.py）

**Files:**
- Modify: `src/finance_agent/llm/probes.py:157-241`（TOOLS 常量后的 tool_call 段）
- Test: `tests/llm/test_probes.py`

**Interfaces:**
- Consumes: `raw_completion`（litellm_adapter，已导入）
- Produces: `run_live_probes` 返回的 ProbeReport 新增 warnings 语义：`tool_call_probe_error`（端点拒绝）、`tool_auto_no_call_forced_ok`（仅强制级通过）；布尔字段结构不变

- [ ] **Step 1: Write the failing tests**

在 `tests/llm/test_probes.py` 的 `TestRunLiveProbes` 类内追加：

```python
    def test_auto_no_call_forced_fallback_passes(self, monkeypatch):
        """两级判定：auto 不调用 + 强制 tool_choice 返回 tool_calls → 通过 + forced_ok warning。"""
        import litellm

        from finance_agent.llm.probes import run_live_probes

        def fake_completion(**kwargs):
            from types import SimpleNamespace

            forced = isinstance(kwargs.get("tool_choice"), dict)
            msgs = kwargs.get("messages") or []
            is_followup = any(m.get("role") == "tool" for m in msgs)
            msg = SimpleNamespace(
                content="好的",
                tool_calls=(
                    None
                    if is_followup or not forced
                    else [
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(name="probe_echo", arguments='{"text":"hello"}'),
                        )
                    ]
                    if kwargs.get("tools")
                    else None
                ),
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="tool_calls")])

        monkeypatch.setattr(litellm, "completion", fake_completion)
        report = run_live_probes(model="openai/kimi-k2-0905-preview", api_key="k", base_url="https://x/v1")
        assert report.tool_call is True
        assert report.tool_followup is True
        assert "tool_auto_no_call_forced_ok" in report.warnings
        assert "tool_call_probe_error" not in report.warnings

    def test_tools_rejected_by_endpoint_marks_error(self, monkeypatch):
        """端点拒绝 tools 请求（HTTP 错误）→ tool_call=false + tool_call_probe_error。"""
        import litellm

        from finance_agent.llm.probes import run_live_probes

        def fake_completion(**kwargs):
            if kwargs.get("tools"):
                raise RuntimeError("400 InvalidSubscription")
            from types import SimpleNamespace

            msg = SimpleNamespace(content="好的", tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])

        monkeypatch.setattr(litellm, "completion", fake_completion)
        report = run_live_probes(model="openai/x", api_key="k", base_url="https://x")
        assert report.non_stream is True
        assert report.tool_call is False
        assert report.tool_followup is False
        assert "tool_call_probe_error" in report.warnings
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/llm/test_probes.py::TestRunLiveProbes -v`
Expected: 两个新测试 FAIL（现单级 auto 判定下：前者 tool_call=False 且无 forced warning；后者无 tool_call_probe_error warning）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/llm/probes.py` 中 tool_call 段（`# tool_call` 注释起至 `except` 块结束）整体替换为：

```python
    # tool_call（两级判定，消除「模型不主动调用」假阴性）：
    # 第一级 auto + 明确工具调用指令；请求成功但未调用 → 第二级指定函数强制
    # tool_choice。任一级拿到结构化 tool_calls 即通过；两级均无 → false；
    # 请求被端点拒绝 → warning tool_call_probe_error（区别于模型未调用）。
    tool_probe_msgs: list = [
        {"role": "user", "content": "请调用 probe_echo 工具，把文本 hello 回显出来"}
    ]
    forced_choice: dict[str, Any] = {"type": "function", "function": {"name": "probe_echo"}}

    def _tool_stage(tool_choice: Any) -> Any | None:
        """单级工具探测：成功返回 message；端点拒绝返回 None 并记 warning。"""
        try:
            r = raw_completion(
                **{**base, "messages": tool_probe_msgs}, tools=TOOLS, tool_choice=tool_choice
            )
            return r.choices[0].message
        except Exception:  # noqa: BLE001
            warnings.append("tool_call_probe_error")
            return None

    tool_msg = _tool_stage("auto")
    if tool_msg is not None and not getattr(tool_msg, "tool_calls", None):
        forced_msg = _tool_stage(forced_choice)
        if forced_msg is not None:
            if getattr(forced_msg, "tool_calls", None):
                warnings.append("tool_auto_no_call_forced_ok")
            tool_msg = forced_msg

    try:
        if tool_msg is not None:
            report["tool_call"] = bool(getattr(tool_msg, "tool_calls", None))

            # tool_followup：构造工具结果回传
            if report["tool_call"]:
                tc = tool_msg.tool_calls[0]
                followup_msgs: list = list(tool_probe_msgs) + [
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": tc.id, "content": "probe-ok"},
                ]
                fr = raw_completion(**{**base, "messages": followup_msgs, "tools": TOOLS})
                report["tool_followup"] = fr.choices[0].message.content is not None
    except Exception:  # noqa: S110
        warnings.append("tool_call_probe_error")
```

（`run_live_probes` 顶部已有 `from typing import Any` 局部导入，无需新增。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/llm/test_probes.py -v`
Expected: 全部 PASS（含既有 `test_all_capabilities_pass`、`test_tool_probe_failure_marks_none`）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/llm/probes.py tests/llm/test_probes.py
git commit -m "fix: [llm] tool_call 探测两级判定消除假阴性（fix-capability-probe-tool-call）"
```

---

### Task 2: test 端点结构化错误（api.py）+ 前端错误文案

**Files:**
- Modify: `src/finance_agent/api.py:1989-1998`（test_llm_config 的 _ensure_prefix 段）
- Modify: `frontend/src/pages/settings/panes/LlmConfigPane.tsx:470-481`（formatTestError）
- Test: `tests/test_api_llm_config.py`

**Interfaces:**
- Consumes: `finance_agent.llm.resolver.UnknownProviderPrefixError`
- Produces: test 端点对前缀错误返回 `success=false, errorType="model_prefix_invalid"`（HTTP 200）；前端 `formatTestError` 识别该码

- [ ] **Step 1: Write the failing test**

`tests/test_api_llm_config.py` 追加（沿用文件既有 TestClient 模式）：

```python
def test_test_llm_config_unknown_prefix_structured_error():
    """未知 provider 前缀 → 结构化失败（errorType=model_prefix_invalid），非 500 裸栈。"""
    with TestClient(app) as client:
        resp = client.post(
            "/api/llm-config/test",
            json={
                "model": "kimi/kimi-k2-0905-preview",
                "baseUrl": "https://api.kimi.ai/v1",
                "apiKey": "sk-test",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["errorType"] == "model_prefix_invalid"
    assert "openai/" in data["error"]
    assert "kimi" in data["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_llm_config.py::test_test_llm_config_unknown_prefix_structured_error -v`
Expected: FAIL（当前抛 UnknownProviderPrefixError → 500）

- [ ] **Step 3: Write minimal implementation**

`api.py` test_llm_config 中，将

```python
    from finance_agent.llm.resolver import _ensure_prefix

    usedModel = _ensure_prefix(usedModel, usedBaseUrl)
    probeModel = usedModel
```

替换为：

```python
    from finance_agent.llm.resolver import UnknownProviderPrefixError, _ensure_prefix

    try:
        usedModel = _ensure_prefix(usedModel, usedBaseUrl)
    except UnknownProviderPrefixError as e:
        # 配置类错误结构化返回（delta：未知前缀不再 500 裸栈），异常文案本身含
        # 已知前缀列表与 openai/<model> 指引
        return {
            "success": False,
            "latencyMs": int((_time.time() - startMs) * 1000),
            "model": usedModel,
            "error": str(e),
            "errorType": "model_prefix_invalid",
        }
    probeModel = usedModel
```

`LlmConfigPane.tsx` 的 `formatTestError` switch 增加 case：

```typescript
    case 'model_prefix_invalid':
      return '模型名前缀不被支持：OpenAI 兼容端点请使用 openai/<模型名>'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_llm_config.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_api_llm_config.py frontend/src/pages/settings/panes/LlmConfigPane.tsx
git commit -m "fix: [api] llm-config/test 未知前缀结构化错误（fix-capability-probe-tool-call）"
```

---

### Task 3: 前端前缀推导白名单回退（llmConfig.ts）

**Files:**
- Modify: `frontend/src/llmConfig.ts:217-235`（buildModelWithPrefix）
- Test: `frontend/src/test/llmConfig.test.ts`

**Interfaces:**
- Produces: `buildModelWithPrefix(rawModel, baseUrl)` 对白名单外前缀回退 `openai/`；白名单常量 `KNOWN_LLM_PREFIXES`（模块内私有）

- [ ] **Step 1: Write the failing tests**

`frontend/src/test/llmConfig.test.ts` 的 `buildModelWithPrefix` describe 内追加：

```typescript
  it('域名推导前缀不在白名单时回退 openai（kimi）', () => {
    expect(buildModelWithPrefix('kimi-k2-0905-preview', 'https://api.kimi.ai/v1')).toBe('openai/kimi-k2-0905-preview')
  })
  it('域名推导前缀在白名单时保持推导值（anthropic）', () => {
    expect(buildModelWithPrefix('claude-sonnet-4', 'https://api.anthropic.com/v1')).toBe('anthropic/claude-sonnet-4')
  })
  it('未知主机兜底段也走白名单回退', () => {
    expect(buildModelWithPrefix('some-model', 'https://foo.bar/v1')).toBe('openai/some-model')
  })
```

注：第三个用例先确认现状——`foo.bar` 推导出前缀 `foo`（bar 在 insignificant 集合），回退后应为 `openai/some-model`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- --run src/test/llmConfig.test.ts`
Expected: 第一个用例 FAIL（现拼出 `kimi/kimi-k2-0905-preview`）

- [ ] **Step 3: Write minimal implementation**

`llmConfig.ts` 在 `buildModelWithPrefix` 上方加常量，并替换 return 行：

```typescript
// 与后端 resolver._KNOWN_PREFIXES 对齐（openai/deepseek/anthropic/gemini）；
// 域名推导出的前缀不在白名单时回退 openai/（OpenAI 兼容端点语义），
// 避免拼出后端解析必然拒绝的前缀（如 api.kimi.ai → kimi/）
const KNOWN_LLM_PREFIXES = new Set(['openai', 'deepseek', 'anthropic', 'gemini'])
```

```typescript
    const prefix = significant[0] || parts[0] || 'openai'
    const safePrefix = KNOWN_LLM_PREFIXES.has(prefix.toLowerCase()) ? prefix.toLowerCase() : 'openai'
    return `${safePrefix}/${model}`
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run src/test/llmConfig.test.ts`
Expected: 全部 PASS（含既有 deepseek/openai 用例）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/llmConfig.ts frontend/src/test/llmConfig.test.ts
git commit -m "fix: [frontend] 模型发现前缀白名单回退（fix-capability-probe-tool-call）"
```

---

### Task 4: 矩阵「未测」态 + warnings 人话化（llmConfig.ts + Pane）

**Files:**
- Modify: `frontend/src/llmConfig.ts`（新增导出 `formatProbeWarning`、`capabilityItemState`）
- Modify: `frontend/src/pages/settings/panes/LlmConfigPane.tsx:356-393`（矩阵渲染 + warnings 渲染）
- Test: `frontend/src/test/capabilityGating.test.ts`

**Interfaces:**
- Produces:
  - `formatProbeWarning(code: string): string`
  - `capabilityItemState(key: keyof CapabilityMatrix, cap: CapabilityMatrix): 'pass' | 'fail' | 'untested'`

- [ ] **Step 1: Write the failing tests**

`frontend/src/test/capabilityGating.test.ts` 追加（文件顶部 import 补 `capabilityItemState, formatProbeWarning`）：

```typescript
describe('capabilityItemState - 矩阵三态', () => {
  const cap: CapabilityMatrix = { non_stream: true, stream: true, tool_call: false, tool_followup: false, json_output: true }
  it('tool_followup 在 tool_call=false 时为未测态', () => {
    expect(capabilityItemState('tool_followup', cap)).toBe('untested')
  })
  it('tool_call=false 为失败态，其余通过项为通过态', () => {
    expect(capabilityItemState('tool_call', cap)).toBe('fail')
    expect(capabilityItemState('stream', cap)).toBe('pass')
  })
  it('tool_call=true 且 tool_followup=false 时 tool_followup 为失败态', () => {
    const c2 = { ...cap, tool_call: true }
    expect(capabilityItemState('tool_followup', c2)).toBe('fail')
  })
})

describe('formatProbeWarning - warnings 人话化', () => {
  it('已知机器码映射为可行动中文提示', () => {
    expect(formatProbeWarning('tool_call_probe_error')).toContain('tools')
    expect(formatProbeWarning('tool_auto_no_call_forced_ok')).toContain('强制')
  })
  it('未知码原样透传', () => {
    expect(formatProbeWarning('something_odd')).toBe('something_odd')
  })
})
```

（`CapabilityMatrix` 若未在该文件 import，顶部补 `import type { CapabilityMatrix } from '../llmConfig'`。）

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- --run src/test/capabilityGating.test.ts`
Expected: FAIL（函数未定义）

- [ ] **Step 3: Write minimal implementation**

`llmConfig.ts` 在 `parseCapability` 后追加：

```typescript
// probe warnings 机器码 → 人话映射（未知码透传）；键与后端 probes.py warnings 对齐
export const PROBE_WARNING_LABELS: Record<string, string> = {
  tool_call_probe_error: '工具调用请求被端点拒绝：请检查该 API 套餐/权限是否支持 tools 参数',
  tool_auto_no_call_forced_ok: '模型未主动调用工具，强制指定后通过（能力正常）',
  json_mode_unsupported: 'JSON 输出模式被端点拒绝，管线结构化节点可能降级',
  stream_unsupported: '流式输出被端点拒绝，快速模式体验可能降级',
}
export function formatProbeWarning(code: string): string {
  return PROBE_WARNING_LABELS[code] ?? code
}

// 矩阵呈现三态：通过 | 不支持（实测失败）| 未测（tool_followup 因 tool_call 未通过而未执行）
export type CapabilityItemState = 'pass' | 'fail' | 'untested'
export function capabilityItemState(key: keyof CapabilityMatrix, cap: CapabilityMatrix): CapabilityItemState {
  if (cap[key]) return 'pass'
  if (key === 'tool_followup' && !cap.tool_call) return 'untested'
  return 'fail'
}
```

`LlmConfigPane.tsx`：import 增加 `capabilityItemState, formatProbeWarning`；矩阵渲染 map 体替换为：

```tsx
              ).map(item => {
                const state = capabilityItemState(item.key, capability)
                return (
                  <div key={item.key} className="flex items-center gap-1.5 text-xs" data-testid={`capability-${item.key}`} data-state={state}>
                    <i
                      className={`fas ${state === 'pass' ? 'fa-check-circle' : state === 'fail' ? 'fa-times-circle' : 'fa-minus-circle'}`}
                      style={{
                        color:
                          state === 'pass'
                            ? 'var(--status-success-default)'
                            : state === 'fail'
                              ? 'var(--status-error-default)'
                              : 'var(--text-tertiary)',
                      }}
                    ></i>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      {item.label}
                      {state !== 'pass' && (
                        <span style={{ color: 'var(--text-tertiary)' }}>{state === 'fail' ? '（不支持）' : '（未测）'}</span>
                      )}
                    </span>
                  </div>
                )
              })}
```

warnings 列表项改为 `{formatProbeWarning(w)}`（key/样式不变）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run src/test/capabilityGating.test.ts src/test/llmConfig.test.ts`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/llmConfig.ts frontend/src/pages/settings/panes/LlmConfigPane.tsx frontend/src/test/capabilityGating.test.ts
git commit -m "feat: [frontend] 能力矩阵未测态与 warnings 人话化（fix-capability-probe-tool-call）"
```

---

### Task 5: 全量验证 + E2E 门禁

- [ ] `uv run ruff check` → 0 error
- [ ] `uv run mypy` → 0 error
- [ ] `uv run pytest tests/llm/ tests/test_api_llm_config.py -v` → 全绿
- [ ] `cd frontend && npm test -- --run` → 全绿
- [ ] E2E 门禁：`cd e2e && npx playwright test`（后端 TESTING=1 stub 套件）→ 全绿；红则 playwright-debugger 诊断
- [ ] 回填 `openspec/changes/fix-capability-probe-tool-call/tasks.md` 勾选
