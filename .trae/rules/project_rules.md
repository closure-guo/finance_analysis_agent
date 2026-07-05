# Finance Analysis Agent

## Test asset locations

测试和验证产物的约定存放位置（不要在根目录创建新目录）：

| 类型 | 路径 | 说明 |
|------|------|------|
| 测试 fixtures | `tests/fixtures/` | 被测数据快照 |
| 验证脚本 | `tests/scripts/` | 手动验证脚本 |
| 验证文档 | `tests/validation/` | 人工验证报告 |
| 运行时报告输出 | `reports/` | docx/pptx 等生成文件（gitignored） |
| E2E 截图/输出 | `tests/e2e/` | 截图、HTML、report_*.md（gitignored） |

**禁止在根目录创建新目录存放测试产物。** 如果需要新的子目录，在上述位置下创建。

## E2E 测试约束

**端到端（E2E）测试禁止使用 mock 数据。** E2E 测试必须使用真实的服务、真实的依赖（如 FastAPI 后端、Vite 前端、真实文件系统）以及真实的输入数据（可来自 `tests/fixtures/`），以验证系统在真实链路下的行为。需要隔离或打桩的场景应放到单元测试或集成测试中，而不是 E2E。

## Incident tracking

问题记录和解决方案维护在 `docs/incidents/`。发现系统性问题时，新建编号文档并更新 README.md 索引。

## Agent skills

### Issue tracker

Issues tracked on GitHub. Use `gh` CLI for all operations. See `docs/agents/issue-tracker.md`.

### Triage labels

Default triage label vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
