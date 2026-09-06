# Design: add-download-center

## 决策

1. **元信息实时扫描而非落库**：导出文件生命周期简单（生成→下载→删除），实时 `os.scandir` 扫描 `REPORTS_DIR` 即可满足列表需求，避免引入文件表与一致性维护成本。文件量预计在百级，扫描开销可忽略。
2. **复用 `/api/files` 命名空间**：现有 `GET /api/files/<file_name>` 下载保持不变；新增无参 `GET /api/files` 作列表、`DELETE /api/files/<file_name>` 作删除，REST 语义自然扩展。路径校验抽为共享工具函数，三类接口统一调用。
3. **删除先动画后请求**：为达成「确认后行立即收起」的流畅体感，采用乐观 UI + 失败回滚（恢复该行 + toast）。文件删除失败率低，回滚成本可接受。
4. **动效实现分层**：hover/过渡类用 Tailwind transition；stagger 入场与删除行高度收起用 framer-motion（`AnimatePresence` + layout 动画），为首个引入 framer-motion 的页面，体积影响约 30KB gzip，可接受。

## 风险

- **并发删除**：用户删除某文件的同时另一会话正在导出同名文件 → 返回 404/500 均属预期，前端回滚提示即可，不加锁。
- **文件名含中文/空格**：下载接口现有逻辑已验证中文文件名（Content-Disposition 编码），删除接口复用同一路径解析，回归测试覆盖。
