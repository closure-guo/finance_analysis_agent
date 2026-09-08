# ehr-style-claim-direction + surgical-citation-repair 验证（2026-09-07）

## ehr-style-claim-direction（任务 3.1-3.3 收尾）

- **Claim.direction 字段**：`Literal["positive","negative","flat"] | None`，非法值
  ValidationError（pydantic）；旧格式 None 走显式降级计覆盖缺口。
- **方向一致性校验**（`_verify_numerical`）：`sign(stated)×direction` 与真值符号对齐，
  符号冲突 FAIL + 新桶 `direction_mismatch`；flat 跳过符号检查；None 跳过方向检查并计
  gap（PASS 也计，与 metric/period 未申报先例一致）。
- **双路径二义消除**：已申报 direction 的 claim 不再走正文方向词核对
  （`internal_inconsistency` 检查短路）。
- **feedback 构造**（citation_node）：direction_mismatch 定向重试条目携带 bucket +
  direction_hint（真值符号 + 「下滑 X% → stated=X, direction=negative」示例）；
  coverage_gap 打回条目携带 direction 补申报提示；direction_mismatch 纳入定向重试桶。
- **词表 11→14 冻结**：补 负增长/跌幅/收窄（语料实证占 2.22%），符号不敏感匹配。
- 测试：23 例 direction 用例（含既有 12 例失败测试）全部转绿；全量 citation 套件 171+
  passed。

## surgical-citation-repair（任务 4.1-4.3 收尾）

- **citation_node 分流接线**（此前 2.6 标勾但未实现——同名测试全部 ImportError）：
  单分析师同轮 value_mismatch <3 → 调 `repair_claims`（真实模块：NLTK 层定位出错句 +
  REPAIR_SYSTEM_PROMPT + 一次 LLM + 整句回填）→ updated_claim 按序写回 → 强制重校验；
  ≥3 / 修复调用崩溃 → 回退全量定向重试（不吞原桶计数）；同处重校验仍 FAIL 不二次修复；
  修复轮共享 iteration_count 与停滞降级语义（成功率 0.0 记入 fail_rates）。
- **遥测**：`value_mismatch_repaired` + surgical_repairs（修前句/修后句/真值/repaired）
  上 trace（update_current_span）；原 value_mismatch 分桶保留（prompt 归因信号）。
- **验证**：
  - 全量后端测试 **2033 passed**（此前基线 1811+）；ruff/mypy 改动文件 0 错误。
  - 全链路用例：TestSurgicalRepair（稀疏/密集/同处不二次/崩溃/停滞 5 例）+
    TestSurgicalRepairIntegration（真实 repair_claims + mock LLM 契约：修复调用→回填→
    重校验 PASS→遥测=1）。
  - bucket 存量复跑（146 trace）：FAIL 305（value_mismatch 17 / path 12 / semantic 34 /
    internal 234…）、D6 残留 unmatched 0；surgical_repair 口径新增且存量=0
    （实现前数据，符合预期无回归）。

## 遗留说明

- 真实 LLM 驱动的一次线全修复（非 mock）需生产管线触发 value_mismatch 场景，随
  nightly @live 与后续真实分析补跑；单点修复 LLM 调用计费与非修复路径一致。