# Tasks: add-context-length-config

- [x] 1. 后端：LLMConfigRequest/LLMConfig 加 contextLength（Pydantic 正整数校验）+ _to_llm_config 透传 + legacy `_request_config_dict` 透传 + resolver 请求级/LLM_MAX_CONTEXT 覆盖 capability.max_context（TDD）
- [x] 2. 前端：设置页「上下文长度」输入（留空默认）+ llmConfig store/payload 持久化与下发（vitest）
- [x] 3. 验证：全量 pytest + 前端 npm test/tsc + E2E 门禁（交互类）；人工抽查后落验证材料
