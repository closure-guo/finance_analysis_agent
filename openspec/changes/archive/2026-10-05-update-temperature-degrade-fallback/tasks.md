# Tasks: update-temperature-degrade-fallback

- [x] adapter 三 raw 入口（raw_completion / raw_stream / raw_acompletion）temperature 拒绝自动降级重试（剔除后重试一次，update_current_span 记 degradation + logger warning），单元测试覆盖：降级成功 / 降级后仍失败原错误上抛 / 非 temperature 错误不触发 / 无 temperature 请求零介入 / async 路径
- [x] 后端 `ruff check` + `mypy`（零新增）+ `uv run pytest tests/llm/ -q` 全绿
- [x] 部署：合并 → 重建 docker backend → 用户复测深度分析（真实 Kimi 思考模型全链路跑通）——backend 镜像 2026-10-05 06:43 重建；600519 真实深度分析 completed（report 7646 字符，零 temperature 拒绝/零降级重试），报告落 tests/validation/2026-10-05-update-temperature-degrade-fallback-validation.md
