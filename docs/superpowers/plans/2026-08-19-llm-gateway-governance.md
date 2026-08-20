# harden-llm-gateway-governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 落地治理层——probe 缓存与事实回写、PolicyRouter 与 fallback 链执行、ContextBudget 按 capability 派生、前端能力矩阵与模式门禁、judge 迁移 gateway 与 drop_params 白名单化。

**Architecture:** probe 事实成为新事实源：`ProbeCache`（进程内 TTL，键=五要素哈希）供 resolver 被动合并（probe 优先静态、未命中标 `probe_required`）；`llm/router.py` 纯选择函数产出 primary+fallback_chain，执行器挂 gateway（合同耗尽/非重试错误依链切换）；ContextBudget 从 capability.max_context 派生；前端消费既有 `/api/llm-config/test` 矩阵（修 snake/camel 失配）；judge 改走 `complete_text(purpose="judge")`；全链迁完移除 `drop_params=True`。

**Tech Stack:** Python 3.12 / pytest / React 18 + TS + vitest。

## Global Constraints

- Delta: `openspec/changes/harden-llm-gateway-governance/`（5 个 spec，validate --strict 已过）；设计档案 §6/§9/§12/§13/§15/§16。
- **子代理禁止 `git checkout`/`git switch`/`git stash` 切换分支或暂存全区**——只允许在当前分支 feat/llm-gateway-51 上 `git add <显式路径>` + commit；禁止 `git add -A`。
- add-llm-provider-gateway 已验收的行为合同（LLMResponse 字段/tuple 流/重试耗尽上抛/观测契约）不得回退；既有测试全绿。
- 前端门禁只看「probe 明确失败」；缓存未命中/超时不禁用（保守放行 + 提示重测）。
- fallback 链长上限 2；切换必须落 trace `fallback_from`；链耗尽上抛原 typed error。
- probe 不修改 provider_options 与密钥。
- 交互类变更（Task 6 前端）适用 E2E 门禁（§3 Step 4.5）。
- commit 格式 `feat(llm)/feat(web)/fix(llm)/chore: ...`。

---

### Task 1: ProbeCache（probe 结果缓存）

**Files:**
- Create: `src/finance_agent/llm/probe_cache.py`
- Test: `tests/llm/test_probe_cache.py`

**Interfaces:**
- Produces:
  - `cache_key(*, model: str, base_url: str | None, api_key: str | None) -> str`：sha256("openai/glm-5.2|https://x/v1|<sha256(key)>|<litellm version>")——provider 由 model 前缀派生；litellm version 经 `importlib.metadata.version("litellm")`
  - `class ProbeCache`: `get(key) -> ProbeReport | None`（TTL 过期返回 None 并清除）、`put(key, report, ttl_seconds=86400)`、`invalidate(key)`；线程安全（`threading.Lock`）；模块级单例 `get_probe_cache() -> ProbeCache`
- Consumes: `llm/probes.py` 的 `ProbeReport`（不变）

**要点：** TDD：命中/过期/TTL 内重复 put 覆盖/键五要素任一变化即不同键（含 api_key hash 与 litellm version 变化）/invalidate。commit `feat(llm): ProbeCache — probe 结果缓存(五要素键+TTL)`。

---

### Task 2: resolver 合并 probe 事实 + /api/llm-config/test 写缓存

**Files:**
- Modify: `src/finance_agent/llm/types.py`（`ModelProfile` 增加 `probe_required: bool = False` 与 `probe_warnings: tuple[str, ...] = ()`，均带默认值向后兼容）
- Modify: `src/finance_agent/llm/probes.py`（`merge_probe_into_profile` 同时把冲突字段名写入 `probe_warnings`）
- Modify: `src/finance_agent/llm/resolver.py`（`resolve_profile` 末尾：查 `get_probe_cache().get(cache_key(...))`，命中→`merge_probe_into_profile` 覆盖 capability + warnings；未命中→`probe_required=True`）
- Modify: `src/finance_agent/api.py` `test_llm_config`（探测成功后 `put` 进缓存，键同上）
- Test: `tests/llm/test_resolver.py` 增补 + `tests/test_api_llm_config.py` 增补

**Interfaces:**
- Produces: resolve_profile 返回的 profile 在有缓存事实时 capability 为 probe 覆盖版且 `probe_warnings` 非空；无缓存时 `probe_required=True`。
- 行为红线：解析期不发起真实探测（只读缓存）；probe 不改 provider_options/api_key。

**要点：** TDD 场景=spec 两个 Scenario（静态 tools!=none + probe tool_call=false → capability.tools=none + warning；无缓存 → probe_required）。既有 resolver 测试全部保持绿（默认无缓存 → probe_required=True 不影响既有断言，除非断言全字段相等——逐一核对）。commit `feat(llm): resolver 合并 probe 事实 + probe_required 标记 + 设置页探测写缓存`。

---

### Task 3: PolicyRouter 纯选择函数

**Files:**
- Create: `src/finance_agent/llm/router.py`
- Test: `tests/llm/test_router.py`

**Interfaces:**
- Produces:
  - `REQUIRED_CAPS: dict[Purpose, dict]`：`{"react": {"tools": {"single","parallel"}}, "pipeline_node": {"json_schema": {"json_mode","strict_schema"}}, ...}`（YAGNI：先 react/pipeline_node 两键）
  - `def select_profile(*, purpose: Purpose, candidates: list[ModelProfile], allow_action_fallback: bool = False) -> RouterResult`
  - `@dataclass RouterResult: primary: ModelProfile; fallback_chain: list[ModelProfile]; trace: dict`（trace 含 profile/provider/model/capability 概要/fallback_chain 名单）
- 规则：硬性 capability 过滤（tools=none 且未 allow_action_fallback → 出局）；fallback 链成员能力 ≥ primary（tools parallel>single、json strict_schema>json_mode 的偏序）；链长上限 2；无候选满足 → 抛 `UnsupportedCapabilityError`；排序：purpose=quick 优先低延迟（capability.max_output 小者优先，简化代理指标）、deep 默认保序。

**要点：** 纯函数无 IO；TDD 覆盖 spec 两 Scenario（弱工具被过滤；parallel primary 不配 single fallback）。commit `feat(llm): PolicyRouter — purpose/硬性能力过滤 + fallback 链选择`。

---

### Task 4: fallback 链执行（gateway 层）

**Files:**
- Modify: `src/finance_agent/llm/gateway.py`（新增 `def complete_text_with_fallback(messages, *, purpose, llm_config=None, trace=None, **kw) -> tuple[str, dict]`：调 router 取链，循环 `complete_text`；捕获 `OutputContractError` 由调用方传入 repair 耗尽语义——**实现放 contracts 调用侧**：简化为捕获 `OutputContractError / ContentFilteredError / AuthError / ModelNotFoundError / UnsupportedCapabilityError`，链未耗尽→换下一 profile（llm_config 换 preset 名）重试并在返回 metadata 写 `fallback_from`；链耗尽→raise 最后错误）
- Modify: `src/finance_agent/llm/contracts.py`（`parse_with_contract` 不改；其调用方 nodes/_llm_utils.py 的 `call_llm_for_json` 增加可选 `fallback_profiles: tuple[str,...]` 参数？——**收敛**：不接线业务，仅提供 gateway 执行器 + 单测，接线留 follow-up，避免牵动管线节点）
- Test: `tests/llm/test_gateway_fallback.py`

**Interfaces:**
- Produces: `complete_text_with_fallback`（签名如上）；`fallback_from` 写入返回 metadata dict；总切换次数 ≤2。
- 边界：**本轮不接线管线/ReAct 业务调用点**（delta task 4 的执行器就绪 + 单测锁定；接线为 follow-up，因接线需 router 候选来源=registry 命名 profile 注册，当前 registry 无 fallback 配置——本任务同时在 registry 给 deepseek-official 填 `fallback=("openai-official",)` 示例链以供测试）。

**要点：** TDD：链切换重试、fallback_from 落 trace、链耗尽上抛、AuthError 不可重试直接走链。commit `feat(llm): fallback 链执行器 — 合同耗尽/非重试错误依链切换 + fallback_from`。

---

### Task 5: ContextBudget 按 capability 派生 + 预算观测字段

**Files:**
- Modify: `src/finance_agent/harness/context.py`（`ContextBudget.__init__` 或工厂 `ContextBudget.from_capability(cap: Capability | None) -> ContextBudget`：max_context_tokens=cap.max_context（None 回落 120000），system_reserve/output_reserve/compact_ratio 保持现比例；新增 `usage_estimated: bool = True` 字段与 `calibrate(usage_total: int | None)` 方法——真值则设 False 并校准 max_context_tokens）
- Modify: `src/finance_agent/harness/loop.py` 仅构造处（`ContextManager(budget=context_budget or ContextBudget.from_capability(...))`——agent 构建处传入当前 profile capability；若 loop 不接触 profile，则在 `agent_factory._make_llm_client` 构造 budget 传入 Agent）——以实际调用链为准，最小改动
- Modify: `src/finance_agent/llm/gateway.py`（`build_trace_metadata` 增加 `max_tokens_source: str = "capability"|"requested"` 与 `usage_estimated: bool`；错误路径 observation metadata 带 `error_type=type(err).__name__`——complete_stream/async/complete_text 三处统一）
- Test: `tests/llm/test_budget_governance.py` + gateway 观测断言增补

**要点：** TDD：200000 capability → 预算 200000；无 usage → usage_estimated=True；calibrate 真值翻转；error_type 落 trace；max_tokens 派生来源 requested/capability 两态。commit `feat(llm): ContextBudget 按 capability 派生 + usage_estimated/error_type/max_tokens_source 观测`。

---

### Task 6: 前端能力矩阵 + 模式门禁（交互类，E2E 门禁适用）

**Files:**
- Modify: `frontend/src/App.tsx`：① 修 `testConnection`（App.tsx:1946-1953 读 `data.latency_ms/error_type` snake_case → 后端实际 `latencyMs/errorType`）；② SettingsModal 渲染能力矩阵（五项 pass/fail 图标 + warnings + probe_required 提示）；③ 模式门禁：`llmConfig store` 增加 `capability` 字段（testConnection 成功后保存 probe 事实）；`EmptyState`/`ChatInputBar` 的 modes 数组按 capability 过滤/禁用（tool_call=false → 深度模式 disabled + 原因文案「该 provider 不支持工具调用，可切换 provider 或使用快速模式」；json_output=false → 管线入口同理）；probe 未命中/超时不禁用。
- Modify: `frontend/src/llmConfig.ts`（store 扩展 capability 持久化）
- Test: `frontend/src/test/capabilityGating.test.ts(x)`（门禁纯逻辑抽成 `canEnterMode(mode, capability)` 函数放 llmConfig.ts 导出，单测：probe 明确 false 禁用、未探测放行、probe 优先静态）

**要点：** 门禁判定抽纯函数先行单测；组件接线后跑 `cd frontend && npm test`；交互类 → `cd e2e && npx playwright test` 门禁（若 e2e 套件不含门禁场景，按 §3 用 playwright-test-generator 补一个设置页矩阵渲染 + 门禁禁用态 spec，selector 来自真实快照）。commit `feat(web): 能力矩阵展示 + 模式入口 capability 门禁(修 snake/camel 失配)`。

---

### Task 7: judge 迁移 gateway

**Files:**
- Modify: `evals/judges.py`（`_call_judge_llm` 改调 `gateway.complete_text(messages, purpose="judge", temperature=0.0, trace={"name":"judge", ...})`；JUDGE_* env 解析经 `resolve_profile(purpose="judge")`（resolver 已有 judge 分支）；删除直连 `litellm.completion` 两处；Langfuse observation 保留 judge environment 审计——trace metadata 带 environment 标记；`import litellm` 移除）
- Test: `tests/evals/test_judges.py` 增补/随迁（mock gateway.complete_text）

**要点：** judge 配置不完整仍显式报错（resolver 既有语义，spec 要求保持）；evals 全量测试绿。commit `feat(evals): judge 迁移 gateway — purpose=judge 统一入口 + environment 审计保留`。

---

### Task 8: drop_params 白名单化移除

**Files:**
- Modify: `src/finance_agent/llm/adapters/litellm_adapter.py`（删除 `litellm.drop_params = True`；新增 `_PARAM_WHITELIST_DROP = {"temperature", "top_p", "frequency_penalty", "presence_penalty"}` 与 `_drop_unsupported(kwargs, capability)`：白名单内且 capability 不支持（如 deepseek thinking 已 suppress 的 temperature 兜底）→ 剔除 + logger.warning；白名单外未知参数 → 保留由 litellm 原生报错，关键参数 guard 已有显式抛错）；环境开关 `LLM_DROP_PARAMS_STRICT=1` 可临时还原旧行为（回滚保险）
- Test: `tests/llm/adapters/test_param_whitelist.py`

**要点：** 前置=Task 7 完成（judge 不再依赖全局 drop）。TDD：白名单剔除+warning、白名单外参数透传、guard 显式抛错不回归、回滚开关生效。**真实验证**：跑一次 `python -m evals.run`（或最小 judge 用例）确认方舟链路无隐藏 drop 依赖；`tests/llm_contracts/` nightly 标记。commit `feat(llm): drop_params 白名单化 — 移除全局静默 drop + 可回滚开关`。

---

### Task 9: 全量验证 + 真实跑批 + 人工验证材料

- `uv run pytest -k "not live" -q` 全绿；`uv run ruff check`；`uv run mypy src/finance_agent`（与基线一致零新增）
- `cd frontend && npm test`；交互类 E2E 门禁：`cd e2e && npx playwright test` 全绿
- 真实：一次 evals 跑批对比基线（judge_failures=0 不回退）+ 设置页 probe → capability 矩阵人工抽查（截图/记录）
- 人工验证报告落 `tests/validation/`（新文件 `2026-08-19-harden-llm-gateway-governance-validation.md`）+ tasks.md 勾选
- commit `chore: harden-llm-gateway-governance 验证材料 + 进度登记`
