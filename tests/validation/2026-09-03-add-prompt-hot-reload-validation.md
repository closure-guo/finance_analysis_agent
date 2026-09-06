# 人工验证报告: add-prompt-hot-reload

**日期**: 2026-09-03
**验证人**: [agent 自动验证 + 端到端演练]
**关联 delta**: openspec/changes/add-prompt-hot-reload/
**E2E 门禁**: 不适用（非交互类变更：无前端/SSE/会话流）

## 验证结果

| Scenario | 覆盖方式 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| TTL 热更新：production 切换后过期生效 | 单测（短 TTL 0.05s） | 等待超过 TTL → 新版本 + version 随动 | test_prompt_loader.py TestTtlHotReload 4 例全绿 | ✅ |
| TTL 窗口内用缓存 / 兜底恢复跟随 / 两接口共享缓存 | 单测 | 收敛延迟可接受、兜底也缓存、一次拉取 | 同上 | ✅ |
| 收编：UI 编辑写回 + 仅含该文件的提交 | 单测（tmp git 仓库） | 文件更新 + 提交只含 alpha.md + 信息含版本 | test_sync_prompts 7 例全绿 | ✅ |
| 冲突保护：本地未提交改动不覆盖 | 单测 | 不写文件 + conflicts + exit 1 | test_conflict_protection | ✅ |
| deploy 预检判别式 | 单测（HEAD 基准） | remote≠local 且 remote≠HEAD → 拒；remote==HEAD → 放行（正常发布） | test_deploy_preflight 8 例全绿（含 HEAD 未知保守拒） | ✅ |
| 真实演练：sync --dry-run | 真实 Langfuse | production 与本地全一致 → 待收编 0 | 实测「待收编 0, 冲突 0」 | ✅ |
| 真实演练：deploy 不可达 host | 真实运行 | 保守拒绝 + 非零退出 | python EXIT=1，预检拦截文案正确 | ✅ |

## 异常记录

1. **实现过程中发现并修正了一个设计缺陷**：第一版预检只比较 `production ≠ 本地` 就拒绝，会把「本地领先的正常发布流」也拦死（本地改完 md 想 deploy 时 production 必然 != local）。修正为以 **git HEAD 为基准**的判别式：`remote == HEAD` 表示 Langfuse 仍在上次提交状态 → 本地领先放行；`remote != HEAD 且 != local` 才是 Langfuse 有未收编变更 → 拒绝。对应 spec「Langfuse 领先时拒绝发布」场景，语义正确。
2. **deep_mode 合并稿收编**（前序工作）与本次热更新链路衔接验证：deep_mode 已回写本地 + 部署（production v9 == 本地逐字一致），sync --dry-run 全一致佐证收编后闭环成立。

## 结论

- [x] 功能实现 + 自动化验证通过（后端门禁 1781 过、前端不受影响、ruff/mypy 干净、三个测试文件 24 例全绿）
- [x] 真实环境演练通过（收编一致路径 + deploy 拒绝路径）
- [ ] 待人工抽查项：TTL 生效观感（改 production 后 ≤30s 新请求用新版，无需重启）、守护进程部署形态（Windows 后台运行方式由用户侧决定）——确认后方可 archive
