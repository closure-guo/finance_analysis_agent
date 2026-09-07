# Incident 025 — opencode zen/go 网关强制 x-opencode-session 头，离线 judge 链路全挂

- **日期**: 2026-09-07
- **状态**: 已修复（适配器补头，见 `1e56692`）
- **影响面**: 所有经 `JUDGE_*` 端点的离线 judge 调用（run_experiment、judge 校准重跑、跨模型一致性重评）——LiteLLM 请求缺 `x-opencode-session` 头 → 网关直接 400 `Request is missing x-opencode-session and cannot be routed efficiently`。

## 现象

- judge 配置（`JUDGE_BASE_URL=https://opencode.ai/zen/go/v1`）下任意模型调用全部抛
  `BadRequestError: ... Request is missing x-opencode-session ...`，包括现行 judge
  `deepseek-v4-flash`。
- 主 LLM（方舟 `LLM_BASE_URL`）不受影响——只有 opencode zen/go 端点要求该头。

## 根因

- opencode zen/go 网关（2026-09 变更）把 `x-opencode-session` 作为**强制**请求头（路由/提示缓存
  优化信号，非凭据，文档要求每会话稳定 id）。仓库 litellm 适配器此前未发送该头，请求被拒。
- 未被及时发现的放大器：08-25 后离线 judge 未再实际运行（09-06/07 的 hosted evaluator 走
  Langfuse UI 独立配置），本地 nightly 因无 LANGFUSE secrets 跳过 → 断裂静默存在约 2 周。

## 修复

- `litellm_adapter.py::_maybe_opencode_session`：`api_base` 含 `opencode.ai` 时注入
  `extra_headers["x-opencode-session"]`（进程级稳定 uuid）；接入 `raw_completion` /
  `raw_stream` / `raw_acompletion` 三个入口。非 opencode 端点不注入，避免行为漂移。
- TDD：`test_litellm_adapter.py` 新增 3 例（opencode 注入 / 非 opencode 不注入 / 流式注入），
  先红后绿；真实 judge 调用经修复后成功。
- 验证报告：`tests/validation/2026-09-07-opencode-session-header-validation.md`（可选补）。

## 防再发

- 适配器是 litellm 唯一入口，所有 opencode 调用自动带该头。
- judge 相关 @live/nightly 测试已具备无 key 跳过纪律；CI secrets 补齐后（需仓库管理员配
  LANGFUSE_* 与 JUDGE_* secrets）离线 judge 链路将回归 nightly 覆盖。