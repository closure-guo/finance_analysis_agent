# frontend delta: replicate-chat-home

## ADDED Requirements

### Requirement: 内容区居中收窄

主内容区 SHALL 以约 `max-w-3xl` 宽度水平居中，消息流、输入区与报告摘要均在居中栏内；视口收窄时 SHALL 自适应为全宽并保留合理内边距。

#### Scenario: 桌面端居中

- **GIVEN** 桌面端视口（≥1280px）
- **WHEN** 打开任意会话
- **THEN** 消息流与输入框 SHALL 居中显示，两侧留白对称

### Requirement: 空态首页

会话无消息时 SHALL 显示空态：居中大号问候语、说明可输入股票名称/代码/自然语言指令的副标题，以及 2–4 张建议卡片；卡片点击 SHALL 将示例文本填入输入框而不直接发送。

#### Scenario: 卡片填入不发送

- **GIVEN** 新会话显示空态
- **WHEN** 用户点击建议卡片
- **THEN** 示例文本 SHALL 填入输入框
- **AND** 不发出分析请求

#### Scenario: 历史会话不显示空态

- **GIVEN** 含消息的会话
- **WHEN** 切换到该会话
- **THEN** SHALL NOT 显示空态，直接显示消息流

### Requirement: 空态退场

首条消息发送后空态 SHALL 以约 200ms 淡出切换为消息流，无布局跳动。

#### Scenario: 发送后空态淡出

- **WHEN** 用户在空态会话发送首条消息
- **THEN** 空态 SHALL 淡出，消息流就位，内容区无跳动
