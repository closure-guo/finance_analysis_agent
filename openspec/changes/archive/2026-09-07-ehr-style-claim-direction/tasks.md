# Tasks: ehr-style-claim-direction

## 1. Claim 模型与校验器（TDD：先写失败测试）

- [x] 1.1 失败测试：Claim 模型接受 direction 字段（positive/negative/flat/None），非法值 pydantic 校验报错
- [x] 1.2 实现 Claim.direction 字段（`src/finance_agent/citation.py`，None 缺省向后兼容）
- [x] 1.3 失败测试：direction="negative" + stated=10.05 + gt=-10.05 → PASS；direction="positive" + gt=-10.05 → FAIL 且 bucket="direction_mismatch"
- [x] 1.4 失败测试：direction=None 旧格式 → 跳过方向检查、计 coverage_gap、不静默
- [x] 1.5 实现方向一致性校验分支 + direction_mismatch 桶（复用 value_mismatch 定向重试路径）
- [x] 1.6 失败测试 + 实现：已申报 direction 的 claim 普查匹配 SHALL NOT 依赖方向词表（双路径二义消除）

## 2. 方向词表兜底降级与补词

- [x] 2.1 失败测试：`_DIRECTION_WORDS` 新增 负增长/跌幅/收窄 的符号不敏感匹配用例
- [x] 2.2 词表扩至 14 词 + 注释冻结声明（后续扩张须评估依据）
- [x] 2.3 失败测试：已申报 direction 的 claim 未命中正文方向词时数字仍认领成功
- [x] 2.4 普查侧按 claim.direction 优先、词表兜底次之的匹配顺序实现

## 3. 重试与打回反馈

- [x] 3.1 失败测试：direction_mismatch 重试反馈携带 ground_truth 符号与 direction 申报示例（tests/nodes/test_citation_node.py::TestDirectionFeedback，先红后绿）
- [x] 3.2 失败测试：coverage_gap 打回条目携带 direction 补申报提示（同上测试类）
- [x] 3.3 实现 citation_node.py 反馈构造：direction_mismatch 条目带 bucket+direction_hint（含真值符号与申报示例）；coverage_gap 条目带 direction_hint；direction_mismatch 纳入定向重试桶

## 4. Prompt 纪律与发布

- [x] 4.1 4 个分析师 prompt（fundamental/technical/sentiment + 辩论者共用段）加 direction 必填纪律与「下滑 X% → stated=X, direction=negative」示例
- [x] 4.2 `uv run python scripts/deploy_prompts.py` 发布并确认 eval 门禁放行
- [x] 4.3 prompt 契约测试更新（agent-prompt-contracts 现有测试套件内补断言）

## 5. 验证与归档前置

- [x] 5.1 全量后端测试 + ruff + mypy 通过
- [x] 5.2 用 tests/scripts/citation_bucket_analysis.py 复跑存量分桶，确认 direction_mismatch 桶埋点出现在新 trace（人工验证：跑 1 次真实/TESTING 管线）
- [x] 5.3 人工验证报告落 tests/validation/（方向判定样例：negative 修饰匹配、direction_mismatch 打回、词表兜底未申报场景）
- [x] 5.4 verification 通过后 openspec archive
