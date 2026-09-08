# frontend delta: add-download-center

## ADDED Requirements

### Requirement: 下载管理入口与路由

侧边栏底部区域 SHALL 提供「下载管理」菜单项（下载图标 + 文字），点击跳转 `/downloads` 路由，主区域渲染下载管理页；直接访问/刷新 `/downloads` SHALL 正常渲染，不丢路由状态。

#### Scenario: 从侧边栏进入下载管理

- **GIVEN** 用户位于任意会话页面
- **WHEN** 点击侧边栏「下载管理」
- **THEN** 路由切换为 `/downloads`，主区域渲染文件列表
- **AND** 侧边栏折叠/展开状态保持不变

#### Scenario: 刷新页面路由保持

- **WHEN** 用户在 `/downloads` 页面刷新浏览器
- **THEN** 页面仍渲染下载管理页而非回退到会话页

### Requirement: 文件列表展示

下载管理页 SHALL 以行列表展示文件：类型图标（docx/pptx/pdf/md 可区分配色）、文件名（超出省略，hover 显示完整名）、格式化大小（KB/MB）、创建时间（当日显示 HH:mm，更早显示 YYYY-MM-DD）、下载按钮与删除按钮（删除按钮 hover 才出现）。列表超屏时内部滚动，标题栏固定。

#### Scenario: 元信息正确渲染

- **GIVEN** 接口返回一个 1.5MB、创建于昨日的 docx 文件
- **WHEN** 页面渲染列表
- **THEN** 该行显示 docx 图标、完整文件名、「1.5 MB」、昨日日期（YYYY-MM-DD）

#### Scenario: 删除按钮 hover 显现

- **GIVEN** 列表存在文件行
- **WHEN** 鼠标未悬停该行
- **THEN** 删除按钮不可见；悬停后淡入显示，行布局不发生位移

### Requirement: 搜索与类型筛选

页面 SHALL 提供文件名搜索框（模糊匹配，实时过滤）与类型筛选（全部/Word/PPT/PDF/Markdown）；两者 SHALL 可叠加生效，筛选切换不重播列表入场动画。

#### Scenario: 搜索叠加类型筛选

- **GIVEN** 列表含 `茅台分析报告.docx` 与 `宁德分析报告.pptx`
- **WHEN** 用户选择「Word」tab 并在搜索框输入「茅台」
- **THEN** 列表仅显示 `茅台分析报告.docx`

### Requirement: 下载与删除交互

点击下载 SHALL 使按钮进入 loading 态（图标转圈 + 禁用），收到响应后恢复并 toast 提示「已开始下载」。删除 SHALL 先弹确认对话框；确认后该行以高度收起 + 淡出动画移除，再调用删除接口；接口失败 SHALL 恢复该行并 toast 报错。

#### Scenario: 删除确认与失败回滚

- **GIVEN** 列表含文件 `a.docx`
- **WHEN** 用户点击删除并在对话框确认，但接口返回 500
- **THEN** 行动画移除后恢复显示
- **AND** toast 提示删除失败，文件仍在列表中

#### Scenario: 取消删除无副作用

- **WHEN** 用户点击删除但在对话框选择取消
- **THEN** 不发出删除请求，列表不变

### Requirement: 空态、加载态与错误态

接口返回空列表时 SHALL 显示空态（占位图形 + 「暂无导出文件」文案 + 返回聊天的按钮）；加载中 SHALL 显示骨架屏；接口失败 SHALL toast 报错且不以空态冒充。

#### Scenario: 无文件时显示空态

- **GIVEN** `GET /api/files` 返回空数组
- **WHEN** 页面加载完成
- **THEN** 显示空态文案与「返回聊天」按钮，点击跳转会话页

#### Scenario: 接口失败不冒充空态

- **GIVEN** `GET /api/files` 返回 500
- **WHEN** 页面加载失败
- **THEN** toast 报错，不显示「暂无导出文件」空态

### Requirement: 交互动效规范

下载管理页动效 SHALL 遵守统一规范：时长三档（150ms 微交互 / 200ms 元素级 / 300ms 页面级）；缓动 ease-out（入场）与 ease-in-out（状态切换）；列表首次进入逐行 stagger 淡入上移（行间隔 30ms），筛选切换不重播；系统开启 `prefers-reduced-motion` 时全部动效 SHALL 退化为无动画。

#### Scenario: 首次进入逐行入场

- **WHEN** 用户首次进入 `/downloads`
- **THEN** 文件行以 30ms 间隔依次淡入并上移归位（fade-in + translateY(8px)→0，200ms ease-out）

#### Scenario: 减弱动效降级

- **GIVEN** 操作系统开启「减弱动态效果」
- **WHEN** 页面渲染与交互
- **THEN** 入场、hover、删除收起等动画全部禁用，状态即时切换
