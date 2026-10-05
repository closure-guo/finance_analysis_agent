## Context

报告管线在 `nodes/report.py` 生成最终 markdown 时，图表 PNG 由 `charts.py` 落在 `tempfile.gettempdir()/finance_charts/<股票代码>/`，图片行以 `![标题](绝对路径)` 形式嵌入 `report_markdown`。导出服务 `export/service.py` 对四种格式复用同一入口 `export_report`：先 `sanitize_missing_images`（删除引用不存在文件的图片行）→ `append_disclaimer` → 按格式转换。docx/pdf/pptx 在转换时读文件嵌入，md 分支仅 `write_text` 落盘——图片外链随之进入产物，在任何消费场景（容器外打开、下载到本机、临时目录清理后）都无法解析。

`report_markdown` 同时是会话持久化、前端报告视图与评估链路（judge 输入）的数据源；`/api/files` 列表/下载/删除与前端下载中心均建立在「一个报告 = 一个文件」的单文件模型上。

## Goals / Non-Goals

**Goals:**

- md 导出产物为自包含单文件：源文件仍存在的图片行改写为 base64 data URI，拷走即用、无外链。
- 缺失图片沿现有降级（跳过该行），与 PDF 行为对齐。
- `report_markdown`、docx/pptx/pdf 三格式、`/api/files` 与下载中心契约零变化。

**Non-Goals:**

- 不做图片压缩/缩放/降采样（体积与 PDF 同量级即可接受）。
- 不改文件夹捆绑/zip 下载路径（已评估并否决，见 Decisions D1）。
- 不处理远程 URL 图片（管线只产本地 PNG；web 图片行原样保留）。
- 不动 `nodes/report.py` 的路径生成逻辑。

## Decisions

**D1 改写时机 = 导出时刻（`service.py` md 分支），不改 `report_markdown` 本身**

- 备选 A（生成时刻把 base64 写进 `report_markdown`）：会话存储每会话膨胀数 MB，前端报告视图与 eval 链路（judge 输入 = state 变量）被大体积编码文本污染——否决。
- 备选 B（文件夹捆绑 `report.md + images/` + 下载打 zip）：与「单文件下载」契约冲突，需改 `/api/files` 列表/下载/删除与前端下载中心；且本系统报告消费场景是本地查看与分发而非 GitHub 发布——否决。
- 结论：`export_report` 是管线自动导出与 `POST /api/export` 的共用入口，在此单点改写两路行为同步收敛，其他消费方零感知。

**D2 处理流程 = 现有 sanitize 之后追加 embed 一遍（md 分支）**

```
现状:  sanitize_missing_images → append_disclaimer → {converter | write_text}
改为:  sanitize_missing_images → append_disclaimer
       ├─ docx/pptx/pdf: converter(...)            # 不变
       └─ md: embed_images_as_data_uris(text) → write_text
```

- sanitize 先行保证 embed 阶段面对的本地图片引用文件必然存在，embed 无需再判存在性，语义不重叠。
- 新增纯函数 `embed_images_as_data_uris(markdown_text: str) -> str`：逐行用现有 `_IMAGE_LINE_RE` 识别独立图片行；路径后缀在 `{.png, .jpg, .jpeg, .gif, .webp}` 映射表内且文件存在 → `base64.b64encode(读字节)` 生成 `![alt](data:image/<mime>;base64,<编码>)`；其余行（含远程 URL、非图片后缀）原样保留。
- 备选（一遍扫描内同时判存在与内嵌）：把 sanitize 与 embed 合并为单遍——省一次遍历但让 md 分支偏离共用 sanitize 语义，四格式行为分叉——否决。

**D3 MIME 判定 = 固定后缀映射表，非图片行不删不改**

管线当前只产 `.png`；映射表覆盖 `.png/.jpg/.jpeg/.gif/.webp`，未知后缀的本地文件引用行**原样保留**（交由既有 sanitize 判存在性），避免误删未知引用。

**D4 编码形式 = 标准 base64（+/=），单行写入**

`data:image/png;base64,<编码>` 替换原路径，其余行结构不动；不引入 URL-safe 变体（主流渲染器按标准字符集解码）。

## Risks / Trade-offs

- [md 文件体积从数十 KB 涨到约 2–4 MB] → 与内嵌同批 PNG 的 PDF 同量级；下载中心已有 size_bytes 展示，用户可感知可控；不做压缩（Non-Goal）。
- [GitHub 等平台剥离 data URI 不渲染] → 本系统消费场景为本地查看/分发；若未来需公开发布，再评估文件夹捆绑（记录于 proposal，不阻塞）。
- [超大单行 data URI 使个别文本编辑器卡顿] → 主流查看场景是渲染器（Typora/VS Code 预览/浏览器）而非纯文本编辑；接受。
- [历史会话临时图已清理时图片静默消失] → 与 PDF 既有降级一致（spec 已有「缺失时优雅降级」场景），非新增缺陷。
- [base64 读取磁盘 IO 失败（如权限）] → embed 函数对读文件异常按「该行原样保留」处理，再由 sanitize 语义兜底？否——sanitize 已先行，存在性已过；读失败属罕见 IO 异常，按单格式失败容错由 `export_report` 外层 `except` 置 `null`（现契约：单格式失败不阻断）。

## Migration Plan

- 纯增量行为变更，无数据迁移：`report_markdown` 存量数据（文件路径引用）在新代码下导出时即时改写；旧 md 产物不追溯重建。
- 回滚 = revert 单 commit，无状态残留。

## Open Questions

（无——方案方向已由用户裁决：base64 内嵌。）
