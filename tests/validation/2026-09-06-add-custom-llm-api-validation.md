# 人工验证报告: add-custom-llm-api（Task 9.6/9.7 收尾）

**日期**: 2026-09-06
**验证人**: ZCode agent（真实 LLM 端到端实测）
**关联 delta**: openspec/changes/add-custom-llm-api/
**前置**: 9.1–9.5 已勾；本报告覆盖最后两项 9.6（真实 LLM 验证自定义 model + base_url）与 9.7（本报告）

## 验证环境

- 后端**真实模式**（非 TESTING），前端 vite + Chromium
- 自定义配置（用户提供的阿里云 MaaS 兼容端点）：
  - model: `openai/deepseek-v4-flash-0731`（openai/ 前缀为 litellm 路由要求，已核对 resolver `_ensure_prefix`）
  - baseUrl: `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
  - apiForm: chat_completion
- 经前端 profile（fa_llm_profiles 激活）→ 请求级 llm_config 下发

## 验证结果

| 验证项 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| 端点连通 | 自定义 baseUrl + key 可用 | `GET {base}/models` 返回模型清单；`deepseek-v4-flash-0731` 直连 chat/completions 推理成功（reasoning 模型） | ✅ |
| 自定义 model+base_url 生效（9.6） | quick 对话走自定义端点 | 修复 quick 通道 llmConfig 透传缺陷后（commit f0e4d29，见下），quick 对话真实推理完成 | ✅ |
| Langfuse 确认模型名（9.6） | trace 中 generation.model = 自定义模型名 | `GENERATION react_agent \| model: openai/deepseek-v4-flash-0731 \| output: yes` | ✅ |
| 真实业务回答质量 | 内容真实非 stub | 「什么是市盈率」回答完整；「茅台最近有什么新闻」触发 web_search 并引用真实 2026 中报数据（营收 922.78 亿 / 提价 1169→1269 等） | ✅ |

## 验证中发现并修复的缺陷（连带成果）

**quick 通道不透传 forwardedProps.llmConfig**（commit f0e4d29，含先红后绿复现测试）：

- 现象：设置面板的自定义 model/baseUrl 在 quick 模式永不生效——端点只读 `apiKey`，`llmConfig` 被静默丢弃；请求落到 env 默认 provider（glm 代理），自定义 key 被对端报「API key format is incorrect」。
- 契约依据：主规范 frontend「Quick Chat Entry」明确「api_key 与 llm_config 经 forwardedProps 透传」——A 类修复（spec 对、代码错）。
- 修复：quick 端点透传 llmConfig（仅接受 LLMConfig 已知字段，畸形载荷静默忽略回退 env），`build_agent(mode="quick", ..., llm_config=...)` 全链路打通。

## 备注

- 首轮深度分析（600519）因东方财富行情接口连接层故障（push2/push2his 连接超时，环境性）失败——管线优雅失败，assistant 给出可操作的错误说明。该故障与本项目代码无关（新浪接口同时段正常，阿里云端点正常）。
- litellm 路由注意点（写入经验）：裸模型名含 `deepseek-` 会被 litellm 路由到 DeepSeek 官方并覆盖自定义 base_url——自定义端点必须带 `openai/` 前缀（resolver `_ensure_prefix` 对无前缀 + baseUrl 已自动补全；带前缀场景需手写）。

## 结论

- [x] 9.6 / 9.7 全部通过，可 archive（任务 66/66）
