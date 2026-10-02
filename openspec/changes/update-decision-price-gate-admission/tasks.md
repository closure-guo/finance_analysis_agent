# Tasks: update-decision-price-gate-admission

- [x] risk_judge 恶化判据分层：残留 ⊆ 首次（source_text 集合 + 条数）→ pass + note「未恶化放行待终裁」；恶化 → fail（TDD：同源残留放行 / 残留新增 source 阻断 / 残留条数增加阻断 三用例；既有 stub 故障注入用例按新分层更新）
- [x] 既有受影响测试回归 + API 阻断测试夹具改恶化形态；全量验证 ruff/mypy/pytest；验证证据落 tests/validation/
