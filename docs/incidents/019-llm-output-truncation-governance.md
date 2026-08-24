# Incident 019: LLM 输出截断治理 — 静默截断、重试空转与 reasoning 配额吃空

**日期**: 2026-08-24
**环境**: 方舟 (Volces Ark) plan/v3 端点 / GLM-5.3 / litellm / gateway 三层架构
**影响**: deep 长 JSON 报告频繁 `finish_reason=length` → 空正文截断、整批 evals item 作废、重试无限空转
**状态**: 阶段修复完成（续写 + 预算对齐官方），遗留 citation 重试放大项

## 现象

- deep 节点（analyst/debate/trader/fund_manager）长 JSON 输出反复 `finish_reason=length`；
  evals 批跑 7 条 deep 全部截断作废，或产出半截 JSON 静默进入下游
- **两条静默路径**：
  1. 异步 `complete_stream_async` 不调 `classify_outcome` → `finish=length` 被 `finished(None)` 当正常结束，**半截内容当完整结果用**（quick/harness 路径）
  2. `complete_text` 只把 `finish_reason` 写 metadata，不检测截断，返回半截 text
- **重试空转**：`_llm_utils.call_llm_streaming` 捕获 `OutputTruncatedError` 后**完整重试 + 预算翻倍**（16384→32768），已生成的 reasoning/正文全部重跑；长节点在 32768 下仍大概率再截
- **reasoning 吃空配额**（incident 017 同族深化）：GLM-5.3 reasoning 与正文**共享 max_tokens**，fundamental_analyst 处理超长财务 JSON，reasoning 阶段吃光 16384 → 正文 `answer=''` → `classify_outcome` 抛 `OutputTruncatedError` 中断整条 item

## 根因（三层叠加）

| 层 | 根因 | 后果 |
|---|---|---|
| 检测 | 异步/非流式入口无归一化截断检测 | length 被静默当正常结束，坏数据进下游 |
| 恢复 | 截断后「完整重试+翻倍」而非「续写缺失尾部」 | 重跑已生成内容，长节点翻倍后仍截断，无限空转 |
| 预算 | `max_tokens=16384` 远低于官方默认 65536，reasoning 共享配额 | reasoning 吃光 → 空正文 → 不可恢复的硬错误 |
| 配置 | `reasoning_effort` 无 GLM 入口（registry/apply_provider_options 仅 DeepSeek） | 无法调低推理消耗，只能靠总量硬撑 |

## 修复（跨 3 个 delta）

### 1. truncation-resume-generation（续写）
- gateway 三入口（`complete_text` / `complete_stream` / `complete_stream_async`）检测 `finish=length` 且正文非空 → 以「已生成尾部 4000 字符 + 进度标注(✅/⏳/⬜) + 剩余预算」发起**续写请求**，拼接输出；续写仍 length → `OutputTruncatedError`（上限 1 轮）
- 进度标注 = `partial_json_progress`（括号栈部分解析，纯函数，可测）+ schema 顶层字段减法
- 异步路径补 `classify_outcome` → 修复「length 静默当正常结束」
- legacy 薄壳整体移除（`migrate-off-legacy-llm-shim`），全部直连 gateway

### 2. align-ark-glm-param-defaults（预算/推理配置）
- `max_tokens` 16384 → **65536**（官方默认，source: docs.bigmodel.cn）；deep 总入口同源统一
- `reasoning_effort` 新增 ark-glm 配置入口（env `LLM_REASONING_EFFORT` / 请求级 / registry 默认 `max`）；**经 `extra_body` 透传**（顶层参数被 litellm openai 路由判 UnsupportedParamsError 拒绝，实测确认）

### 3. 附带修复（同批发现）
- `complete_stream` 累积变量移出 `try`：`raw_stream()` 抛异常时 except 引用未绑定 `_answer` → evals Item 9-16 全败根因
- akshare 1.18.63→1.18.94（东财反爬适配，push2 断连）
- `tests/scripts/test_litellm_stream.py` 改 `verify_*`（防 pytest 误收集连网挂死）

## 验证

- 真实验证（2026-08-24，全链路就绪）：16 条 dataset 全部跑完并判定，**无一条因截断中断**；8 条 deep 全产出分数
- 全量 `pytest -m "not live"` **1185 passed**
- 截断后「重试完整重跑」→「续写补尾部」：已生成内容不再丢弃

## 遗留

1. **citation 重试放大**：每条 deep 因 `citation_pass=False` 把 4 分析师完整重跑 3 轮（分×3），耗时 30+ 分钟/item；根因是 prompt 示例 `field_ref` 带占位符（`profitability_metrics.roe.<index>`）与 state 真实字段路径不匹配 → `_resolve_field_ref` 逐层取不到判 FAIL。65536 解决截断后此问题成为主要耗时源，**单独立项**。
2. **decision_grounding 低分**（真实实验均值 1.57/5）：交易决策论据缺乏可追溯的前文引用，judge 判定低；**单独立项**。
3. `LLM_REASONING_EFFORT` 对 deepseek 分支仍生效（legacy 语义保留），GLM 走 ark 通道，两套并存待收敛。
4. `harness/litellm_client.py`（quick ReAct）保留 `max_tokens=16384`（legacy 合同保真），与 deep 的 65536 分层，属有意决策。