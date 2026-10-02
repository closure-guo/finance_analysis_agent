# Design: update-sell-action-typing

## Approach

渐进分型，action 枚举不动（非 BREAKING），消费方按 sell_type 分流：

1. **schema（models.py）**：`sell_type: Literal["exit", "short"] | None = None` + `exit_schedule: str | None = None`；validator：sell_type 大小写归一、"reduce"/"减仓"/"退出"→exit、"做空"/"裸空"→short 的同义词容错仅收首版词表（exit/short 字面 + 大小写），杂值归 None（走默认 short 路径）。非 sell 动作的 sell_type 归 None（防 LLM 在 buy 上塞值）。
2. **校验（validate.py `final_price_missing` + risk_judge）**：
   - `final_price_missing`：action=sell 且 sell_type=exit → 豁免 entry/stop/target，改为检查 exit_schedule（缺失记入 missing 列表，note 文案区分「减仓节奏」）；sell_type=None/short → 现行行为。
   - risk_judge：sell 且 sell_type 为 None → 新增轻量打回（【sell 分型申报打回】反馈说明双型语义），重试一次；仍缺 → 默认 short + final_check note「sell_type 未申报，默认 short 模板」。打回复用一次预算，不与价位打回叠加（sell_type 判定在价位检查前：exit 直接改走豁免分支，避免无意义价位打回）。
3. **渲染（report.py `_format_trade_decision`）**：sell_type=exit → 方向行「sell（减仓）」+ 减仓节奏行 + 不渲染三价位行与派生指标行；short/None → 现行。exit_schedule 缺失「未申报」。
4. **prompts**：trader.md 第 36/45/54/61 行区域改写 sell 语义为双型 + 申报要求；risk_judge.md 同步终稿契约段。改后必须 `uv run python scripts/deploy_prompts.py`（prompt-deploy-consistency 门禁）。
5. **结算（零改动声明）**：judgment.py `direction_for_action` 的 sell→short 对 exit 结算数学一致（均价格下跌获益）；注释补声明。track-record 的 entry_price 语义在 exit 下为空——ingest 侧 entry_price None 已有处理（历史 watch/hold 先例）。
6. **范围外**：buy 侧对称分型、滞回联动（后续）、回测 driver 的 exit 专门回测口径（track-record 数据积累后另立）。

## Alternatives Considered

- **action 枚举拆分（sell→exit+short 两个 action）**——不选：BREAKING 所有消费方（结算/回测/track-record/前端），且历史数据迁移成本高；渐进字段分型可平滑过渡。
- **exit 复用 stop_loss 当「恢复持有线」**——不选：字段语义复用会让校验/结算/回测三处都做特判，比新字段贵；reeval_triggers 已是重新介入条件天然载体。
- **只在 prompt 层改语义不改 schema**——不选：LLM 申报无结构化落点会被 validator 丢弃，等于没改。

## Risks

- **LLM 申报率**（sell_type 缺失高频）→ 打回一次 + 默认 short 兜底，行为不劣于现状；申报率进观测（final_check note 统计口径后续挂 evals）。
- **exit 的价位豁免被滥用**（LLM 借 exit 逃避价位申报）→ exit_schedule 必填申报 + 减仓节奏自由文本进报告可见；滥用形态（exit_schedule 空洞如「择机减仓」）首版不设内容质量校验，观测先行。
- **prompt 部署漂移**——deploy_prompts 门禁已有（prompt-deploy-consistency），照流程走。
