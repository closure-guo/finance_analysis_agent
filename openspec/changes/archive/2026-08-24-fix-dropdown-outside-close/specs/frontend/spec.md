# Delta for frontend

## ADDED Requirements

### Requirement: Dropdown Outside-Click Dismissal
系统 SHALL 在「模式切换」与「LLM 切换」下拉框展开后，支持点击下拉框以外的页面区域将其关闭，且同一输入栏内的两个下拉框互斥展开（打开一个时自动关闭另一个）。

#### Scenario: 空状态首页模式下拉框点击外部关闭
- **GIVEN** 空状态首页，模式切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** 模式切换下拉框关闭
- **AND** 当前模式不变，不触发任何输入发送动作

#### Scenario: 会话底部输入栏模式下拉框点击外部关闭
- **GIVEN** 会话视图，底部输入栏的模式切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** 模式切换下拉框关闭
- **AND** 当前模式与会话不变，不触发新会话

#### Scenario: 空状态首页 LLM 切换下拉框点击外部关闭
- **GIVEN** 空状态首页，已配置至少一个 LLM profile，LLM 切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** LLM 切换下拉框关闭
- **AND** 当前 LLM profile 不切换

#### Scenario: 会话底部输入栏 LLM 切换下拉框点击外部关闭
- **GIVEN** 会话视图，已配置至少一个 LLM profile，底部输入栏的 LLM 切换下拉框已展开
- **WHEN** 用户点击下拉框以外的页面区域
- **THEN** LLM 切换下拉框关闭
- **AND** 当前 LLM profile 不切换

#### Scenario: 同一输入栏两个下拉框互斥展开
- **GIVEN** 空状态首页，模式切换下拉框已展开
- **WHEN** 用户点击同一输入栏内的 LLM 切换触发按钮
- **THEN** 模式切换下拉框关闭，LLM 切换下拉框展开
- **AND** 反向操作同样生效：LLM 切换下拉框展开时点击模式切换触发按钮，LLM 切换下拉框关闭、模式切换下拉框展开

#### Scenario: 再次点击触发按钮收起
- **GIVEN** 模式切换或 LLM 切换下拉框已展开
- **WHEN** 用户再次点击同一触发按钮
- **THEN** 下拉框关闭

#### Scenario: 点击选项执行动作并关闭
- **GIVEN** 模式切换或 LLM 切换下拉框已展开
- **WHEN** 用户点击下拉框内的某个选项
- **THEN** 执行该选项对应动作（切换模式 / 切换 LLM profile）
- **AND** 下拉框关闭
- **AND** 模式选项的 capability 门禁（`canEnterMode`）逻辑保持现状：门禁不允许的模式选项仍禁用且点击不生效