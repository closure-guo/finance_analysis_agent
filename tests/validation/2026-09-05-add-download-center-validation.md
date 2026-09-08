# 人工验证报告: add-download-center

**日期**: 2026-09-05
**验证人**: ZCode agent（真实 Chromium GUI 实测 + API 实测）
**关联 delta**: openspec/changes/add-download-center/
**E2E 门禁**: stub 套件 `npx playwright test --grep-invert "@live"` → 20 passed / 2 skipped / 0 failed（2026-09-05，downloads.spec 在门禁内）

## 验证环境

- 后端 TESTING=1（REPORTS_DIR 指向测试目录，预置中文文件名导出文件）
- 前端 vite dev server，Chromium 1280×800

## 验证结果

| 验证项 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| 中文文件名下载 | 「贵州茅台_600519_….docx」可下载 | 页面 download 事件触发；`/api/files/{URL编码名}` GET 200 | ✅ |
| 路径穿越拒绝 | `../` 穿越请求被拒 | `GET /api/files/..%2F..%2Fpyproject.toml` → 404 | ✅ |
| 删除二次确认 | 先弹「确定删除…不可恢复」再删 | 对话框含文件名 + 取消/删除按钮 | ✅ |
| 删除失败回滚 | DELETE 500 → 列表回滚 + 错误提示 | 劫持 DELETE 返回 500：行保留 + 「删除失败，请重试」toast | ✅ |
| 成功删除 + 空态 | 删除后行移除，删空显示空态 | 确认后行移除；空列表渲染「暂无导出文件」（downloads-empty） | ✅ |
| 接口失败不冒充空态 | /api/files 500 → 错误态非空态 | 劫持 500 后重进页面：显示「加载失败 / 重试」，无假空态 | ✅ |
| 刷新页面路由保持 | /downloads 刷新后仍渲染下载管理页 | **发现缺陷**：存在持久化会话时 boot 恢复把路由拉回 /（见下） | ✅（修复后） |

## 验证中发现并修复的缺陷

- **现象**：`fa_current_session_id` 有持久化值时，在 /downloads 刷新页面被重定向回首页。
- **根因**：boot 恢复（restore-session-on-refresh）复用 `selectSession`，其内「pathname !== '/' 则 navigate('/')」把全页路由拉回首页。E2E 门禁此前未发现是因为 spec 的 storageState 无持久化会话。
- **修复**：`selectSession` 增加 `opts.skipHomeRedirect`，boot 恢复调用时跳过抢路由（用户点会话仍回聊天首页）；回归测试 downloadCenter.test.tsx「有持久化会话时直达 /downloads 仍保持路由」。
- **修复后复验**：同路径实测刷新后保持 /downloads + 下载管理页渲染 ✅；前端 9/9 该文件全绿。

## 动效说明

首次进入逐行入场与减弱动效降级（framer-motion reducedMotion 断言）由组件测试 downloadCenter.test.tsx 覆盖，GUI 人工复核动效属主观项，以组件断言为准。

## 结论

- [x] 全部通过（含 1 项缺陷修复回填），可 archive
