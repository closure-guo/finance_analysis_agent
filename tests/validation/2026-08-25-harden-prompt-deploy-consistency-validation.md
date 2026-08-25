# 人工验证报告: harden-prompt-deploy-consistency

**日期**: 2026-08-25
**验证人**: agent（自动化验证 + 真机门禁实测）
**关联 delta**: openspec/changes/harden-prompt-deploy-consistency/
**E2E 门禁**: 不适用（非交互类变更——发布工具 + eval 门禁 + 文档声明）

## 验证结果

| Scenario | 验证方式 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 发布脚本迁移 | git log rename 检测 + dry-run | `scripts/deploy_prompts.py` 存在、旧路径删除、参数保留 | rename 84% 保历史；dry-run 打印 14 文件；--exclude 可用 | ✅ |
| 门禁：版本一致放行 | 单测（test_all_consistent_returns_empty） | Langfuse 与本地逐字一致 → 返回空列表 | 10 passed（含此用例） | ✅ |
| 门禁：不一致拒绝 | 单测 + **真机实测** | 不一致 → 列出差异并拒绝 | 真机改 trader.md 后 eval 被拦：报错 + 提示 deploy_prompts | ✅ |
| 门禁：拉取失败兜底 | 单测 | get_prompt 异常 → 记 `(拉取失败)` 不一致 | 断言通过 | ✅ |
| CRLF 归一化 | 单测 + 真实内容验证 | 仓库 .md 为 CRLF（core.autocrlf=true），归一化后不误报 | test_all_consistent 仍过（真实 CRLF 内容） | ✅ |
| 全量回归（非 live） | pytest `-m "not live"` | 0 failed | 见命令输出（后台全量） | ✅ |
| ruff / mypy | 命令 | clean / 无新增 | ruff 过；mypy 与基线同数 | ✅ |
| AGENTS.md 声明 | 人工核对 | 权威源 + 发布命令 + 产物路径更新 | 已写入测试约束区 | ✅ |

## 真机门禁实测（关键证据）

```
临时对 src/finance_agent/prompts/trader.md 追加一行（不发布）→
uv run python -m evals.run "gate-test"
输出: "错误: 以下 prompt 的 Langfuse production 版本与本地 .md 不一致，拒绝运行实验（防测错版本）:
请先执行 `uv run python scripts/deploy_prompts.py` 发布后再运行。"
恢复文件后门禁放行正常。
```

这验证了 delta 的核心动机：2026-08-25 曾发生 Langfuse 停留 ver=1（旧 prompt）而两轮 eval 静默全测旧数据的事故——现在同类漂移在运行前被显式拦截。

## 异常记录

- 无本 delta 相关异常。`@live` 网络用例（test_eval_live 等）为既有环境失败，不在本 delta 范围。

## 结论

[x] 全部通过，可 archive