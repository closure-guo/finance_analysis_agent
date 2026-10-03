# 验证报告: fix-capability-probe-tool-call（自动化部分）

**日期**: 2026-10-03
**验证人**: ZCode（自动化）；真实 provider 复测项待用户人工验证
**关联 delta**: openspec/changes/fix-capability-probe-tool-call/
**E2E 门禁**: 见 §3（非 @live 23 绿；2 红 = main 基线同款存量，非回归）

## 1. 单元/集成测试

| 套件 | 命令 | 结果 |
|---|---|---|
| probe 判定层 | `uv run pytest tests/llm/ -v` | 全绿（含新增两级判定 2 例） |
| test 端点 | `uv run pytest tests/test_api_llm_config.py -v` | 17 passed（含新增结构化错误 1 例） |
| 合计 | `uv run pytest tests/llm/ tests/test_api_llm_config.py -q` | **320 passed** |
| 前端 | `cd frontend && npm test -- --run` | **643 passed**（含矩阵三态/warnings 映射/前缀回退新用例）；`tsc -b --noEmit` 干净 |

新增测试先红后绿（TDD）：
- `test_auto_no_call_forced_fallback_passes`（红：旧单级 auto 判定下 tool_call=False）
- `test_test_llm_config_unknown_prefix_structured_error`（红：旧代码 500 裸栈）
- `buildModelWithPrefix` kimi/foo.bar 两例（红：旧推导拼出 `kimi/`、`foo/`）
- `capabilityItemState`/`formatProbeWarning` 5 例（红：函数未定义）

## 2. 静态检查

- `uv run ruff check`：All checks passed
- `uv run mypy`（api.py + probes.py）：5 错误全部与 main 同款存量（1296/1998↔main 1997/398/1110），**零新增**；CI 本就 `|| true` 容忍

## 3. E2E 门禁（交互类变更）

环境注意（重要运维事实）：本机 docker 生产栈占 8000/5173，playwright `reuseExistingServer: true` 会**误复用 docker 旧代码**（首次运行 13 passed 实为测 docker，smoke 404 即证据）。正确流程：停 docker backend/frontend → 门禁拉起 worktree TESTING 后端 + vite → 跑完恢复。

| 运行 | 范围 | 结果 |
|---|---|---|
| worktree 分支代码 | 非 @live 全量 | **23 passed, 3 skipped** |
| worktree 分支代码 | eval-ops-console 单独 | 2 failed（cohort「已开启」vs 前提「未开启」等） |
| **main 基线对照** | eval-ops-console 单独 | **4 failed**（含 worktree 同款 2 个） |

结论：eval-ops 2 红 = **本地环境存量态**（data/ 下 cohort/正式批状态残留），main 基线更红，非本分支回归；@live 7 例对 stub 后端按设计必挂（StubLLMClient 不吐 tool_call，spec 注释明示 nightly 职责）。核心链路（smoke/streaming/agui/concurrent-streaming/session-switch/downloads/sidebar）在分支代码上全绿。CI（干净环境 + 无 live 凭据）为最终门禁。

## 4. 待人工验证（用户执行）

1. **真实 Kimi 端点复测**：设置页填 Kimi base_url/api_key，模型自动发现选 kimi 模型 → 确认自动填充 `openai/kimi-k2-...`（不再 `kimi/`）；点「测试连接」→ 矩阵应显示 工具调用 ✓（或警告含人话提示）；若模型不主动调用，warnings 出现「模型未主动调用工具，强制指定后通过」且工具调用仍 ✓
2. **深度模式解锁**：探测通过后重启后端（清 24h probe 缓存里的旧 ✗ 事实）→ 深度模式可进入且 /api/analyze 不再报 `capability.tools=none`
3. **未测态目视**：造一个 tool_call=false 的 provider → 「工具跟随」显示灰色「未测」而非红「不支持」
4. 前缀非法路径：模型名手填 `kimi/xxx` 测试 → 失败提示「模型名前缀不被支持：OpenAI 兼容端点请使用 openai/<模型名>」（非 500）

## 5. 结论

- [x] 自动化验证全部通过（单测/集成/静态/E2E 门禁按上述口径）
- [ ] 人工验证（§4）待用户执行后回填，全过后方可 archive
