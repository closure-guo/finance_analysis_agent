# Design: upgrade-judge-material-v8-rubric

## Context

round8 代裁报告（docs/evals/2026-09-13-round8-维护者代裁报告.md）确认 judge 无虚高但存在两类可修缺陷：材料侧（consistency 缺 Trader 方案节、debate 缺收敛信号骨架）与 rubric 执行侧（debate 5 分档把关不一致、dg 归属层多源同判误扣）。judge 变量组装集中在 `evals/extract.py: extract_judge_vars`（11 变量），rubric 与模板在 `evals/judges.py`，材料锚点在 `evals/judge_calibration/material.py`。当前 consistency 的 `risk_judgment` 变量 = `final_trade_decision`（Risk Judge 裁决后）+ 风险辩论尾部，Trader 原始方案（`state.trade_decision`，Layer III 输出）从未进任何 judge 变量。

## Goals / Non-Goals

**Goals**
- consistency judge 可核对「Trader 方案 → Risk Judge 裁决」是否静默推翻
- debate 材料自带收敛信号骨架，judge 不必从原始发言自行推断
- 两条 v8 判例直接写进 rubric 文本，消除 round8 代裁发现的执行偏差
- rubric 版本递增（debate 3→4、consistency 3→4、dg 7→8）并按校准门禁纪律重校准

**Non-Goals**
- 不改 5 层流水线、citation 链路、前端
- 不引入 LLM 预摘要环节（见决策 2）
- 不拆多轮实验（见决策 4）

## Decisions

### 1. Trader 方案节取 `state.trade_decision`（Trader 原始输出），非 `final_trade_decision`
否则对照对象是 Risk Judge 自己，静默推翻无从谈起。`extract_judge_vars` 新增 `trader_plan` 变量 = `_serialize_decision(state.get("trade_decision"))`，复用现有序列化与 `_trunc` 预算。`final_trade_decision` 为 None 时（trader 未产出）给空串，模板空节跳过——与现有变量缺失行为一致。
**备选否决**：让 Risk Judge 材料自含「与 Trader 方案的 diff」——在节点层做，侵入流水线，超出本 delta 范围。

### 2. 收敛信号 = 确定性统计骨架，不用 LLM 预摘要
骨架行内容：回合数、各方每轮论点数、R2 逐条回应判定（复用现有交锋覆盖统计）、让步/坚持语计数（正则匹配「确实/同意/部分接受/合理性」vs「不同意/恰恰相反/反驳」类标记词），标注「程序统计，供参考」。SUM 一行，置于原始发言之前。
**备选否决**：LLM 预摘要——引入第二个模型输出进 judge 输入，既加成本又引入无法审计的中间偏差源，与「观测数据会撒谎」纪律冲突。
**已知限制**：正则启发式有假阳/假阴，靠「供参考」定位降权，judge 仍以原文为准。

### 3. 判例写进 rubric 正文，不做独立 few-shot 机制
两条判例直接以「判例：」段写进对应 rubric（debate 5 分档定性论点判例、dg 多来源归属判例），措辞直接引用 round8 代裁报告的两个误判案例（比亚迪 ref7、美的/宁德满分行）。维持单模板渲染，不引入 few-shot 组装复杂度。

### 4. round9 单轮混合变量 + 预登记声明
材料升级与 rubric v8 同轮上线，metrics.md §2 预登记按混合变量轮声明（round8 先例），按桶归因。**备选否决**：拆材料轮/rubric 轮两轮实验——token 成本翻倍，n=9 样本无统计力区分两轮差异，得不偿失。

### 5. 校准对照基线 = round8 代裁 41 行
非盲对照（代裁报告已声明口径限制），重点验证两条判例的定向效果：比亚迪 ref7 型归属不再误扣、美的/宁德型满分行被降 4。dg 中段均分预期小幅上移（4 分档收窄），属预期内变化，记时间线时注明。

## Risks / Trade-offs

- [材料长度增加挤压 _trunc 预算] → trader_plan 与骨架行均在既有 `_trunc`/`_append_within_budget` 机制内，回归时核对 consistency 材料完整性（round7 回归先例：标注人看不到全部章节）
- [trade_decision 键在部分旧会话 state 缺失] → 变量空串 + 模板空节跳过，不报错
- [收敛启发式误判误导 judge] → 骨架行强制标注「程序统计，供参考」；代裁审计时专项核对该行
- [rubric 版本递增触发校准门禁重跑] → 按纪律执行 round9 + 代裁审计，这正是本 delta 目的

## Migration Plan

纯评估侧变更，无数据迁移。上线顺序：代码 + 测试合入 → round9 预登记 → 跑实验 → 代裁审计 → metrics.md 时间线/runs.jsonl → 归档 sync。回滚 = revert judges.py/extract.py 提交（rubric 版本号随 revert 回退）。

## Open Questions

- 无（实验排期与判例取舍已在 round8 代裁报告与 metrics.md 待决策节闭环）
