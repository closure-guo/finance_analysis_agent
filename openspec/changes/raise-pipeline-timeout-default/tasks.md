# Tasks: raise-pipeline-timeout-default

- [x] 默认预算常量化共享（`PIPELINE_TIMEOUT_DEFAULT_SECONDS`），agent_factory 与 pipeline_runner 均引用，默认 2400
- [x] 单测钉住默认常量（防回退收窄）
- [x] 全量验证：uv run pytest / ruff check / mypy 通过
- [x] `PIPELINE_TIMEOUT_SECONDS=0` 显式禁用超时（ReAct + fast path 双路径，单测覆盖慢流完整跑完不判失败）
- [x] docker-compose 后端环境置 0（本部署取消时间限制，用户决策 2026-08-26）
