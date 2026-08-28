# Tasks: add-llm-api-form

- [x] 设置面板展示「API 形式」下拉框（OpenAI Chat Completion / Anthropic Messages / OpenAI Responses 三选项），未设置时为空
- [x] Profile 持久化 `apiForm`，切换 profile 时表单与请求同步切换
- [x] 请求级 `llm_config.apiForm` 下发，后端映射为 litellm `api` 参数（`chat` / `messages` / `responses`）
- [x] 裸模型名前缀推导：`chat_completion`/`responses`→`openai`、`messages`→`anthropic`；已含 `/` 前缀原样使用；未设 `apiForm` 不推导
- [x] 未设置 `apiForm` 时保持 litellm 自动路由现状（行为与升级前一致）
- [x] 非法 `apiForm` 值返回配置错误（HTTP 422），不静默忽略
- [x] 单测覆盖：前端 payload 构建与前缀推导、后端映射/校验（非法值拒绝）
- [x] 后端测试全绿（`uv run pytest`）+ Lint（`uv run ruff check`）+ 类型检查（`uv run mypy`）
