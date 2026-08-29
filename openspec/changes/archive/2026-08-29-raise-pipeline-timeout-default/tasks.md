# Tasks: raise-pipeline-timeout-default

- [x] 默认预算常量化共享（`PIPELINE_TIMEOUT_DEFAULT_SECONDS`），agent_factory 与 pipeline_runner 均引用，默认 2400
- [x] 单测钉住默认常量（防回退收窄）
- [x] 全量验证：uv run pytest / ruff check / mypy 通过