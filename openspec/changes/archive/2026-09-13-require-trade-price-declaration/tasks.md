# Tasks: require-trade-price-declaration

## 1. 测试先行

- [x] 1.1 validate 测试：buy + 三价全 None → price_check fail（attempts=0），feedback 列明缺失项与申报要求
- [x] 1.2 validate 测试：buy + entry 有值但 stop None → fail 列明 stop；sell + target=0 → fail（0 计为缺失）
- [x] 1.3 validate 测试：attempts≥1 且仍缺失 → pass + note「已打回仍未申报」（放行，不进 corrected）
- [x] 1.4 validate 测试：watch + 价位缺失 → 直通不变；价位齐备 → 既有校验行为不变（回归锁定）

## 2. 实现

- [x] 2.1 `validate.py`：buy/sell 价位缺失分支由「静默 pass」改为 fail 判定（缺失项清单进 feedback），二次仍缺失放行+note；缺失不进参考带修正路径
- [x] 2.2 `prompts/trader.md`：buy/sell MUST 申报 entry/stop/target 数值价位（watch/hold 豁免），示例与说明同步
- [x] 2.3 `prompts/risk_judge.md`：裁决继承价位——可按风险辩论调整数值，MUST NOT 置 null

## 3. 发布与验证

- [x] 3.1 `uv run pytest` 全量绿（非 live）+ `uv run ruff check` + mypy 触碰文件零新增
- [x] 3.2 `uv run python scripts/deploy_prompts.py` 发布 prompt（eval 门禁依赖）
- [x] 3.3 真实运行验证：buy 决策带真实价位的完整报告（辩论引用代码派生值一致 + 报告参数行渲染数值）——**待 Docker/Langfuse 恢复后补跑**，人工核对记录落 tests/validation/
- [x] 3.4 tasks 全勾后 `openspec archive`，spec sync 合入主规范 `openspec/specs/price-level-tooling/`
