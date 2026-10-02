# Tasks: update-sell-action-typing

- [x] schema：sell_type/exit_schedule 字段 + 归一 validator（TDD：合法双型/同义词大小写/杂值归 None/非 sell 归 None）
- [x] 校验与打回：final_price_missing exit 豁免三价位+必填 exit_schedule；risk_judge sell_type 缺失打回一次→默认 short+标注（TDD：exit 缺节奏打回 / 缺型打回后申报 / 仍缺默认 short）
- [x] 渲染分模板：exit 渲染减仓节奏不渲染建仓行；short/None 现行（TDD 三形态）
- [x] prompts：trader/risk_judge sell 双型语义与申报要求 + `deploy_prompts.py` 发布 + prompt 契约断言更新
- [x] 结算零改动声明（judgment.py 注释）+ 全量验证（ruff/mypy/pytest）+ 验证报告
