# citation-verification Delta

## ADDED Requirements

### Requirement: 修复回填后强制重校验

单点修复回填正文后，系统 SHALL 立即重跑完整 citation 校验（值容差、术语/期次一致性、coverage 普查全路径），并以重校验结果作为该轮最终校验状态。修复 SHALL NOT 跳过或豁免任何校验分支（含方向检查，若方向 delta 已落地）；改写引入的新错误 SHALL 照常按既有分桶暴露并进入既有重试/放行路由——修复回路 SHALL NOT 吞错。若重校验后同处仍 FAIL，该 claim SHALL 回退至目标分析师全量重试路径（若轮次与阈值允许）或按既有放行规则处理，SHALL NOT 对同处 claim 连续发起第 2 次单点修复。

#### Scenario: 修复成功以重校验为准

- **WHEN** 出错句「净利润下滑 10.4%」被改写为真值一致的表述并回填
- **THEN** 系统 SHALL 重跑完整校验，全部通过时该轮 citation_pass 判 PASS

#### Scenario: 修复引入新错不吞错

- **WHEN** 改写回填后重校验发现同句新数字与真值仍超容差
- **THEN** 该 claim SHALL 照常判 value_mismatch FAIL 并按既有路由处理，SHALL NOT 因「已修复过」而放行

#### Scenario: 同处不二次单点修复

- **WHEN** 某 claim 经单点修复回填后重校验仍 FAIL
- **THEN** 系统 SHALL NOT 对该 claim 再次发起单点修复

### Requirement: 修复遥测与原桶保留

单点修复 SHALL 在 Langfuse trace 留痕：修前句、修后句、ground_truth、重校验结果。被修复的 claim SHALL 保留原 value_mismatch 分桶计数并追加 `value_mismatch_repaired` 遥测口径——修复 SHALL NOT 从分桶统计中抹除原失败信号（prompt 优化的归因依据）。

#### Scenario: 修复留痕可归因

- **WHEN** 某轮 1 条 value_mismatch 经单点修复后 PASS
- **THEN** trace SHALL 同时可见：原 FAIL 记录（value_mismatch 桶）、value_mismatch_repaired 标记、修前修后句与真值
