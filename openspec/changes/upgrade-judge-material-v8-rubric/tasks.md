# Tasks: upgrade-judge-material-v8-rubric

## 1. rubric v8（evals/judges.py）

- [ ] 1.1 RUBRIC_VERSIONS 递增：debate_quality 3→4、consistency 3→4、decision_grounding 7→8，注释补 v8 变更说明（来源：round8 代裁报告两处执行偏差）
- [ ] 1.2 debate_quality rubric：5 分档追加「判例：论点列表中任一条为纯定性表述（无数据/事实支撑的断言，含『历史上……』类无样本论据）即降 4，即使该回应其余部分数据密集」
- [ ] 1.3 decision_grounding rubric：归属层追加「判例：同一评判在多个来源均有原话时，引用任一真实来源即合法；仅当所有被标来源均无原话才按错安处理（降 1 档、不高于 4）」
- [ ] 1.4 consistency 模板：新增【Trader 方案】{{trader_plan}} 节 + rubric 核对句「Risk Judge 裁决相对 Trader 方案是否有未说明的方向/参数推翻」

## 2. judge 材料升级（evals/extract.py + judge_calibration/material.py）

- [ ] 2.1 extract_judge_vars 新增 `trader_plan` 变量 = `_serialize_decision(state.get("trade_decision"))`（空缺失给 ""）
- [ ] 2.2 `_summarize_debate` 骨架行追加收敛信号（回合数/各方论点数/让步与坚持语计数，强制标注「程序统计，供参考」）
- [ ] 2.3 material.py `sections_for_dimension` 锚点更新：consistency 加【Trader 方案】、debate_quality 加骨架行节

## 3. 测试

- [ ] 3.1 tests/evals/test_judges.py：版本断言更新（debate==4、consistency==4、dg==8）+ v8 锚点（纯定性判例/多来源归属判例/Trader 方案核对句）
- [ ] 3.2 extract 测试：trader_plan 变量（有值/缺失空串）、骨架行收敛信号输出格式
- [ ] 3.3 全量回归 `uv run pytest` + `uv run ruff check` + mypy 触碰文件零新增

## 4. 实验 round9

- [ ] 4.1 metrics.md §2 预登记 round9（混合变量轮声明：材料升级 + rubric v8；对照基线 = round8 代裁 41 行；定向验证点：比亚迪 ref7 型归属、美的/宁德型满分行）
- [ ] 4.2 跑 round9 实验（dataset a-share-analysis-v1），健康检查 → runs.jsonl + 时间线
- [ ] 4.3 代裁审计：重点核两条判例定向效果，结论落 docs/evals/ 代裁报告追加节

## 5. 收口

- [ ] 5.1 tasks 全勾 + verification 后 `openspec archive`，spec sync 合入主规范 `openspec/specs/evaluation/`
- [ ] 5.2 BACKLOG 第 5 条（round9 + v8 候选）标记闭合
