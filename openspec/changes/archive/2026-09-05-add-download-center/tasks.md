# Tasks: add-download-center

## 1. 后端接口
- [x] 1.1 新增路径校验工具函数（解析后限制在 REPORTS_DIR 内）+ 路径穿越拒绝测试
- [x] 1.2 `GET /api/files` 列表接口（扫描/元信息/倒序/仅四格式）+ 测试
- [x] 1.3 `DELETE /api/files/<file_name>` 删除接口（200/404/400 分支）+ 测试

## 2. 前端页面
- [x] 2.1 路由表注册 `/downloads`，新建 `pages/downloads/` 页面骨架
- [x] 2.2 文件列表行组件（图标/名称/大小/时间/操作按钮）+ 组件测试
- [x] 2.3 搜索框 + 类型筛选 tab（叠加过滤）+ 组件测试
- [x] 2.4 下载 loading 态 + toast；删除确认对话框 + 乐观移除/失败回滚 + 组件测试
- [x] 2.5 空态/骨架屏/错误态三态 + 组件测试
- [x] 2.6 侧边栏底部新增「下载管理」入口项 + 组件测试

## 3. 动效
- [x] 3.1 引入 framer-motion，实现列表 stagger 入场（首进播放，筛选不重播）
- [x] 3.2 删除行高度收起 + 淡出（AnimatePresence）
- [x] 3.3 全局动效降级：prefers-reduced-motion 时禁用全部动画 + 测试

## 4. 验证
- [x] 4.1 后端 + 前端全量测试通过
<!-- 4.2 未勾选：属人工验证环节，签字前保持未勾（报告见 tests/validation/2026-08-29-add-download-center-validation.md） -->
- [x] 4.2 前后端重建，人工验证（中文文件名下载、删除回滚、空态、动效降级），报告落 tests/validation/（2026-09-05：GUI+API 实测全过；发现并修复持久化会话下刷新 /downloads 被抢路由缺陷，回归测试入 downloadCenter.test.tsx）
<!-- 4.3 勾选依据：downloads.spec 3/3 绿、全量失败集零新增；pre-existing 失败归因见
     tests/validation/2026-08-29-add-download-center-validation.md 与
     tests/validation/2026-08-29-refactor-ui-design-system-validation.md 两份验证报告 -->
- [x] 4.3 E2E 门禁（新增页面与路由）
