# 人工验证报告: add-portfolio-beta-alpha

**日期**: 2026-10-03
**验证人**: ZCode(agent,自动化部分)+ [待人工补签]
**关联 delta**: openspec/changes/add-portfolio-beta-alpha/
**E2E 门禁**: 默认套件 + track-record 专属套件(5 passed,含新 β/α spec)+ timeline 套件

## 验证结果

| Scenario | E2E 已覆盖? | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 快照有值 → β=0.85 / α=+3.10% 两格渲染 | 是(track-record-beta-alpha.spec.ts #1) | 精确文本 | 自动化通过 | ✅ |
| 样本不足 → 两格显示 "—" | 是(#2) | "—" 且其余指标不受影响 | 自动化通过 | ✅ |
| 指标计算正确性(β=0.8 线性构造/α=−0.004/样本门槛) | 后端集成测试覆盖 | 精确断言 | 79 相关用例全过 | ✅ |
| 旧库迁移(存量 agent_metrics_daily 补列幂等) | 后端单测覆盖 | 双跑不重复加列 | 通过 | ✅ |
| 两格视觉(间距/副标题文案与主题一致) | 否 | 与既有指标卡风格一致 | **待人工抽查** | ☐ |
| 真实数据读数(净值 ≥20 重叠日后两格亮起) | 否 | β 反映当前净空结构(可能为负) | **合并后需手动重算指标快照,数值待人工核读** | ☐ |

## 自动化验证证据(2026-10-03,worktree .worktrees/beta-alpha)

- `uv run ruff check`: All checks passed
- `uv run mypy src/`: 81 errors = 分支基线 81(mypy 对本 feature 零新增)
- `uv run pytest`(全量): **3954 passed** / 7 skipped / 6 failed——6 个失败**全部**为 `*_live`/`LiveContractProbe`(需真实 LLM API);抽验报错为上游端点 `OpenAIError(422, "Missing model or messages")` + `completion_tokens=0`,系当日 live API 服务端可用性劣化(同批测试当日早间在 #203 分支全量时通过),与分支代码无关,@live 类测试本就不进门禁
- `cd frontend && npm test`: **632 passed**(76 文件)
- E2E 默认套件: 24 passed / 2 @live skipped
- E2E track-record 专属套件(独立测试库): **5 passed**(index-compare 3 + beta-alpha 2);文件序不破坏空库前提(beta-alpha 只写 agent_metrics_daily,build_index_compare 不读该表)
- E2E timeline 套件: **21 passed / 1 skipped**(本次无 flaky)
- 本地复跑专属套件前需删 `data/test-e2e-track-record.db*`(CI 不受影响)

## 合并后操作说明

1. 本 PR 叠在 PR #203(feat/index-performance-compare)之上:**先合 #203,本 PR 自动变为可合**(或按 GitHub 提示 retarget main);两分支都改过 TrackRecordPage.tsx 与 api.py,若手动 rebase 遇 hunk 相邻冲突属预期,手工可解
2. `docker compose up -d --build backend frontend`(两个镜像都要)
3. 手动重算指标快照使两格亮起: `docker exec finance-agent-backend-1 python -c "from finance_agent.outcome.track_record.marking import persist_metrics_snapshot; print(persist_metrics_snapshot())"`(净值重叠日收益对 ≥20 后才非 null;当前 17 点 → 首次亮起约在下个交易周)
4. 人工核读:β 预期为负值或低值(净空结构),α 接近 0——两格数值需结合「跌市高回避」语境解读,不得直接读成选股能力(见会话讨论:β 是敞口、α 是剔除大盘后的残差)

## 异常记录

- 无阻断性异常。已记录:①全量 pytest 的 6 个 live 失败归因上游 API 可用性(证据见上);②专属 config 头注释在 glob 化后个别措辞陈旧(不影响行为,挂账);③与 #203 的文件接触面(api.py seed 块、TrackRecordPage.tsx)hunk 相邻,顺序合并即可,无需手工解冲突

## 结论

[ ] 全部通过,可 archive
[ ] 存在失败项,需修复后重新验证

> 结论栏待人工完成「两格视觉」与「真实读数核读」后勾选(后者需先执行合并后操作说明 2-3 步)
