# 人工验证报告: update-track-record-display-clarity

**日期**: 2026-10-08
**验证人**: ZCode agent（用户委托的自动化人工验证环节，真实生产数据抽查 + 截图核验）
**关联 delta**: openspec/changes/update-track-record-display-clarity/
**E2E 门禁**: tests/e2e/playwright 专属套件 13/13 全绿（含新增 track-record-ux-clarity.spec.ts 4 用例；清库复跑两轮，最后一轮为 key 碰撞修复后 HEAD 3c9772c1）
**堆叠说明**: 本分支基于 add-current-stance-view（PR #260），验证页面含当前观点区

## 验证环境（真实生产数据）

worktree 后端（8005，`SESSIONS_DB_PATH` 指向生产 `data/sessions.db`，只读端点）+ worktree 前端 vite dev（5179，`VITE_API_TARGET`→8005）。验证时点库内实况：total=92、open=66、dup=14、resolved_neutral=12、legacy_open=7、settled=0、open 行无盯市记录（106 条历史 marks 全属已关闭期观点）。未触碰生产容器。

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 口径披露行双计数 | 是（E2E legacy_open 断言） | settled/legacy_settled=0 →「无存量」；legacy_open=7 →「另有 7 条旧口径进行中，不计入头条口径」 | 披露行实况「存量旧口径：无存量 + 另有 7 条旧口径进行中，不计入头条口径」（DOM + 截图双确认） | ✅ |
| 样本量术语消歧 | 是（duplicates spec 断言已更新） | 横幅「已结算 0 条」，不再出现「已判定 0 条」 | 横幅实况「样本积累中（已结算 0 条，满 10 条解锁胜率）」；全页无「已判定 0 条」 | ✅ |
| 切片空态折叠 | 是 | settled=0 → 一行说明、无分桶表格 | 「切片指标将在首批观点结算后可用」，四维表格消失（原来全「—」+未知桶主导的区域不再占屏） | ✅ |
| 窗口列混合口径 | 是（T+20/T+252 并存断言） | 每行显示自带 horizon | 中信建投 T+20；关键字过滤 300750 → 宁德时代行「T+252」如实可见（09-06 旧口径行不再无法分辨） | ✅ |
| 副标题去 20 日硬编码 | 是（not.toContainText） | 「仍在判定窗口内(长短见「窗口」列)」 | 副标题实况符合 | ✅ |
| 同日重复折叠 | 是（×3 折叠/展开/total 不变） | 同股同日连续 dup 折叠为「同日重复 ×n」，点击展开，total 不变 | 真实数据 688072 10-02 组「同日重复 ×7」；展开后明细行出现（行级计数含组外行共 18 行确认明细行渲染）；分页 total 143 恒定 | ✅ |
| open 行浮动收益（无盯市路径） | 是（有盯市正向 + 无盯市「—」） | 有 latest_mark 显示浮动车+盯市日期 title；无则「—」 | 生产 open 行均无 marks → 全部「—」+「未结算」标注（如实，无 0 值冒充）；正向场景由 E2E 种子 marks 覆盖（-1.20%/-0.80% + title×2） | ✅ |
| 详情页中文化 | 是（看空 exact + 规则中文） | 方向「看空」(title=short)、判定规则「被新观点替代·提前结算」(title=superseded) | 光大银行 09-29 看空行详情页：两处中文渲染、title 保留英文原值、无裸「short」主展示 | ✅ |
| 带内中性标签 | 是 | resolved_neutral 行标签「带内中性」 | 已判定 tab 光大银行行显示「带内中性」（与方向「中性」不再同词） | ✅ |

## 异常记录

1. **折叠 key 碰撞 bug（人工验证发现，已修复于 3c9772c1）**：首次核验 688072 时观察到两个同 testid 汇总行（×4 与 ×7）——组 key 原为 `symbol|date`，生产数据存在同股同日多段连续 dup（段间被日主行隔开）时撞 key，且展开状态互相串扰。修复=key 加首行 prediction_id（结构上不可能再碰撞），vitest 补多段独立性回归用例，E2E 改正则定位。修复后实况单组 ×7 展开正常。×4 段的成因判定为「过滤切换中途的截断页瞬态渲染」（未过滤 page-1 尾部截断 dup 运行 + 过滤后数据先后渲染；updated_at 证实期间无数据变更），修复后不可复现。
2. 验证环境注：5178 端口被上一轮验证的残留 vite 进程占用（TaskStop 未清净 Windows node 子进程），本轮改用 5179；该残留进程属 add-current-stance-view 工作区，未处置（避免误杀并发会话进程）。
3. `.superpowers/sdd/` 草稿区发现其他会话的计划报告文件（task-migrate-*/task-5.5，12:18 写入），与本变更无关，未触碰。

## 端到端验证补充（2026-10-08 下午，用户要求追加）

**范围**：默认 stub E2E 套件（真实浏览器 + 真 LLM stub 全链路，此前按 incident 038 教训留给 CI 的部分）+ 深度管线→落库→展示的完整用户旅程。

| 项 | 结果 | 归因证据 |
|---|---|---|
| 默认 stub 套件 | 24 passed / 9 failed / 2 skipped | 9 失败（search-banner @live×3、thinking-banner @live×3、deep-thinking-toolcall @live×1、eval-ops-console×2）在堆叠基线（无本分支改动）**原样复现**——@live 用例需真 LLM、eval-ops 需调度器环境，非本分支回归 |
| track-record 专属套件 | 13/13（见上） | — |
| 深度管线 spec（report-export，timeline 套件） | 初次在本分支连续 4 失败（管线以空 stock 元数据降级完成、无观点落库） | **判定为环境瞬态而非代码回归**：①失败全部集中在 15:31-15:44 时间窗（疑似行情源限流），其后 6 连过横跨所有代码组合（基线×2、双基线、双分支、混合、分支冷跑）；②git 二分（api.py/model.py 分别换回基线）无稳定归因；③离线复现 ingest 在分支代码上正常落库；④最终分支 HEAD 冷跑（删 cache.db+删库）**通过**。该 spec 的数据源依赖 flaky 属既有已知形态（参见 e2e 手动套件陈旧史），留观 |
| **全链路旅程**（隔离库 e2e-journey/test-e2e-sessions，TESTING=1 stub LLM + 真实行情） | ✅ | UI 发起深度分析 → 5 层管线完成 → **观点落库实锤**（600519.SH neutral open T+20 入场 180.00）→ 战绩页「当前观点」区与观点日志同时呈现该新观点（截图存档）；窗口列/已结算措辞/切片空态/口径披露在新产数据上全部正确 |

**结论补充**：端到端验证通过。运行环境已还原（backend/frontend 容器重启且 healthy；临时端口进程已清理；隔离测试库为 worktree 本地 scratch，不影响生产）。

## 结论

- [x] 全部通过，可 archive（PR 合并后执行 sync + archive；本报告即 tasks 3.3 的人工验证产物）
