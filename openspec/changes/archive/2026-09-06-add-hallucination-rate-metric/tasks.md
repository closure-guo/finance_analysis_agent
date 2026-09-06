# Tasks: add-hallucination-rate-metric

## 1. claim 抽取（v1：数值型规则抽取）

- [x] 1.1 失败测试先行：抽取结构与 contradicted/unverifiable 判定（tests/evals/test_hallucination.py 9 例）
- [x] 1.2 数值型 claim 规则抽取（价格/涨跌幅/市值/PE/PB/ROE）；事实型 claim 抽取需 LLM 标后续增量

## 2. 校验与指标

- [x] 2.1 证据源对接：verify_claims 对照数据映射（AKShare quote 可离线提供 price/市值/PE/PB；缺失 → unverifiable 如实标注）
- [x] 2.2 hallucination_rate = contradicted / 可验证总数（容差按类型配置：价 ±2%、涨跌 ±0.5pp、市值 ±10%、PE ±1、PB ±0.5、ROE ±1pp）

## 3. 门禁

- [x] 3.1 fixtures 零违例为确定性门禁（clean 报告 rate=0）；nightly @live 真实报告+行情监控（tests/evals/test_hallucination_live.py，无 key 跳过、行情失败降级 unverifiable）
- [x] 3.2 幻觉率上限阈值接入评测门禁报表（待指标积累形成基线后设阈值）——**待办**（2026-09-06 落地：HALLUCINATION_MAX_RATE 宽松初值 10% + GATE_MIN_N=5 小样本不判定，门禁判定入报表、CI exit code 语义；报告 tests/validation/2026-09-06-add-hallucination-rate-metric-validation.md）

## 4. 验证

- [x] 4.1 uv run pytest / ruff / mypy 全绿；本机 @live 真跑产出 reports/hallucination-report-20260904.md（10 claims，行情源缺失时全 unverifiable）
- [x] 4.2 事实型 claim（LLM 抽取）增量——**待后续（需 LLM 余额）**（2026-09-06 落地：extract_factual_claims 经 llm.invoke 抽取、无 LLM/坏 JSON 优雅回退空、无证据源如实 unverifiable 不进分子；LLM 可注入 evals judges 同款客户端）
