# Incident 017: 方舟 GLM-5.2 reasoning 吃满 max_tokens 配额 — 管线行失败

**日期**: 2026-08-16
**环境**: 方舟 (Volces Ark) plan/v3 端点 / GLM-5.2 / litellm 1.85.1
**影响**: evals 跑批行级失败（JSONDecodeError 炸整行）、quick/follow_up 空输出
**状态**: 已修复（max_tokens 4096→16384 + parse 尾逗号容错）

## 现象

- 死锁修复（incident 016）后复现跑批，两行 deep 均 FAILED：
  `JSONDecodeError`（"Illegal trailing comma" / "Unterminated string at char 4299" /
  "No JSON object found: char 0"）从 `graph.invoke` 冒出
- 分析师层有降级（"降级为原始文本报告"），下游节点（debate/trader/risk/
  fund_manager）`parse_json_response` 裸奔无 try/except → 单次坏输出炸整行

## 根因（两层）

**层 1（源头）**：方舟 GLM-5.2 **强制 thinking 不可关**（`thinking.type=disabled`
被端点 400 拒绝；`reasoning_effort` 参数 litellm 层即拒收），且 **reasoning 与
正文共享 max_tokens 配额**。实测简单问题 reasoning 即 ~2500 token / 4500+ 字符。
管线默认 `max_tokens=4096`（harness 路径未传、依赖端点默认）→ reasoning 挤占
配额 → 正文截断（char 4299 ≈ 4096 token 上限）或 content 全空（char 0）。

llm.py 的 thinking/reasoning_effort 分支为 DeepSeek 专属（`_is_deepseek`），
GLM 走标准分支 — `.env` 的 `LLM_REASONING_EFFORT=low` 对 GLM 无效（注释已修正）。

**层 2（容错）**：`parse_json_response` 的 `raw_decode` fallback 自身抛出的
JSONDecodeError（尾逗号等）未被捕获，直接冒出到无保护的节点层。

## 修复

- `llm.py` 三入口默认 `max_tokens` 4096→**16384**（上限不影响计费，按实际用量）
- `harness/litellm_client.py` 显式传 `max_tokens=16384`（原先不传）
- `parse_json_response`：raw_decode 失败后清理尾逗号（`,]`/`,}`）重试；
  仍失败才 raise（保留上游降级信号）
- `.env` 注释修正：GLM 不支持 effort 调节

测试：`tests/nodes/test_parse_json_tolerance.py`（尾逗号 5 用例 + 错误路径 2 用例）

## 验证

`tests/scripts/repro_baseline_deadlock.py 0 1`（与跑批同路径，跑批最易失败的
前两行 deep）：
- 修复前：row 0 FAILED 243s（尾逗号）、row 1 FAILED 529s（空输出）
- 修复后：row 0 DONE（report 12927 字符）、row 1 DONE（10236 字符，上次
  死锁卡死行）、进程正常退出、threads=6 稳定
- 行耗时 4→17 分钟属预期：reasoning 配额放开后输出更完整

## 遗留

- 下游节点解析失败无降级是**显式设计**（fund_manager 注释：不静默降级为
  approve），如需重试/降级语义属行为变更，须走 OpenSpec delta
- quick/follow_up 空结果待跑批复验（大概率同源已修复）
