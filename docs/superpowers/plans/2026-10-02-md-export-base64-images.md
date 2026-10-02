# MD 导出图片 base64 内嵌 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** md 导出产物自包含——引用存在的本地 PNG 图片行在导出时刻改写为 `data:image/png;base64,...` 内嵌，图片不再依赖临时目录绝对路径。

**Architecture:** 在共用导出入口 `export_report`（`src/finance_agent/export/service.py`）的 md 分支追加一遍纯文本改写：新增纯函数 `embed_images_as_data_uris`，位于现有 `sanitize_missing_images` 之后（sanitize 先删缺失引用，embed 只面对存在文件）。docx/pptx/pdf 转换路径、`/api/files` 契约、会话存储 `report_markdown` 均不变。

**Tech Stack:** Python 3.12 标准库（`base64`、`pathlib`）；pytest。

**关联:** openspec change `update-report-export-md-images`（proposal/specs/design 已 validate --strict 通过）；delta spec：`openspec/changes/update-report-export-md-images/specs/report-export/spec.md`。

## Global Constraints

- 只用标准库，不新增依赖（`base64` 为 stdlib）
- 注释与 docstring 中文，风格对齐 `service.py` 现状
- `sanitize_missing_images` 与 docx/pptx/pdf 路径零改动；改写仅发生在导出时刻，`report_markdown` 本身不变
- MIME 判定用固定后缀映射 `{.png,.jpg,.jpeg,.gif,.webp}`；非图片后缀行、远程 URL 行**原样保留**
- 缺失文件行不得由 embed 删除（删除语义归 sanitize；embed 对缺失保守保留原行）
- 测试命令一律 `uv run pytest ...`；commit 中文描述 `feat: [export] ...`
- 实施在隔离 worktree 进行（主检出有并发会话使用）

---

### Task 1: `embed_images_as_data_uris` 纯函数

**Files:**
- Modify: `src/finance_agent/export/service.py`（顶部 import 区 + `sanitize_missing_images` 之后）
- Test: `tests/export/test_service.py`

**Interfaces:**
- Consumes: 现有 `_IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")`（service.py:27）
- Produces: `embed_images_as_data_uris(markdown_text: str) -> str`——Task 2 的 md 分支调用

- [ ] **Step 1: Write the failing test**

在 `tests/export/test_service.py` 的 import 行改为：

```python
import base64

from finance_agent.export.service import (
    append_disclaimer,
    embed_images_as_data_uris,
    export_report,
    sanitize_missing_images,
)
```

文件末尾追加：

```python
def test_embed_images_replaces_existing_png_with_data_uri(tmp_path):
    img = tmp_path / "chart_roe.png"
    raw = b"\x89PNG\r\n\x1a\n" + b"chart-bytes"
    img.write_bytes(raw)
    text = f"# 报告\n\n![ROE 趋势]({img})\n\n正文"

    result = embed_images_as_data_uris(text)

    encoded = base64.b64encode(raw).decode("ascii")
    assert f"![ROE 趋势](data:image/png;base64,{encoded})" in result
    assert str(img) not in result
    assert "正文" in result


def test_embed_images_keeps_missing_file_line_as_is():
    text = "# 报告\n\n![坏图](C:/不存在/图.png)\n\n正文"
    assert embed_images_as_data_uris(text) == text


def test_embed_images_keeps_non_image_suffix(tmp_path):
    note = tmp_path / "data.txt"
    note.write_text("x", encoding="utf-8")
    text = f"# 报告\n\n![附件]({note})"

    assert f"![附件]({note})" in embed_images_as_data_uris(text)


def test_embed_images_keeps_remote_url():
    text = "![网图](https://example.com/a.png)"
    assert embed_images_as_data_uris(text) == text


def test_embed_images_passes_plain_text_through():
    assert embed_images_as_data_uris(_SAMPLE.rstrip("\n")) == _SAMPLE.rstrip("\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/export/test_service.py -v -k embed`
Expected: FAIL——`ImportError: cannot import name 'embed_images_as_data_uris'`

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/export/service.py` 顶部 import 区加：

```python
import base64
```

`sanitize_missing_images` 函数之后追加：

```python
# md 自包含导出：仅内嵌常见位图后缀；未知后缀/远程 URL 行原样保留
_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def embed_images_as_data_uris(markdown_text: str) -> str:
    """将引用存在的本地图片文件的图片行改写为 base64 data URI（md 自包含导出）。

    前置约定：sanitize_missing_images 已先行删除缺失文件引用；此处对缺失文件
    保守保留原行，不承担删除语义。远程 URL 与非图片后缀行原样保留。
    """
    out_lines = []
    for line in markdown_text.splitlines():
        m = _IMAGE_LINE_RE.match(line.strip())
        suffix = Path(m.group(2)).suffix.lower() if m else ""
        if m and suffix in _MIME_BY_SUFFIX:
            img_path = Path(m.group(2))
            if img_path.exists():
                encoded = base64.b64encode(img_path.read_bytes()).decode("ascii")
                out_lines.append(f"![{m.group(1)}](data:{_MIME_BY_SUFFIX[suffix]};base64,{encoded})")
                continue
        out_lines.append(line)
    return "\n".join(out_lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/export/test_service.py -v`
Expected: PASS（新 5 例 + 存量 6 例全绿）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/export/service.py tests/export/test_service.py
git commit -m "feat: [export] 新增 embed_images_as_data_uris——md 导出图片行改写 base64 data URI"
```

---

### Task 2: `export_report` md 分支接入

**Files:**
- Modify: `src/finance_agent/export/service.py:88-89`（md 分支）
- Test: `tests/export/test_service.py`

**Interfaces:**
- Consumes: Task 1 的 `embed_images_as_data_uris(markdown_text: str) -> str`
- Produces: `export_report` md 产物为自包含单文件（对外签名不变）

- [ ] **Step 1: Write the failing test**

`tests/export/test_service.py` 末尾追加：

```python
def test_export_report_md_embeds_existing_image(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    img = tmp_path / "chart_roe.png"
    raw = b"\x89PNG\r\n\x1a\n" + b"chart-bytes"
    img.write_bytes(raw)
    report = f"# 报告\n\n![ROE 趋势]({img})\n\n正文"

    result = export_report(report, "600519", "贵州茅台", formats=("md",))

    content = Path(result["md"]).read_text(encoding="utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    assert f"data:image/png;base64,{encoded}" in content
    assert str(img) not in content
    assert "免责声明" in content
    # 会话侧 report_markdown 不被改写（改写仅发生在导出时刻）
    assert report == f"# 报告\n\n![ROE 趋势]({img})\n\n正文"


def test_export_report_md_drops_missing_image_line(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    report = "# 报告\n\n![坏图](C:/不存在/图.png)\n\n正文"

    result = export_report(report, "600519", "", formats=("md",))

    content = Path(result["md"]).read_text(encoding="utf-8")
    assert "![坏图]" not in content
    assert "正文" in content


def test_export_report_md_no_data_uri_without_images(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "", formats=("md",))

    content = Path(result["md"]).read_text(encoding="utf-8")
    assert "data:image" not in content
    assert "免责声明" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/export/test_service.py -v -k "md_embeds or md_drops or md_no_data"`
Expected: `test_export_report_md_embeds_existing_image` FAIL（content 仍是绝对路径、无 data URI）；`md_drops` 与 `md_no_data` 现状即绿（回归守卫）

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/export/service.py` 的 `export_report` 内，将：

```python
            if converter is None:  # md：直接写文本
                Path(target).write_text(markdown_text, encoding="utf-8")
```

替换为：

```python
            if converter is None:  # md：图片内嵌为 data URI，落盘自包含单文件
                Path(target).write_text(
                    embed_images_as_data_uris(markdown_text), encoding="utf-8"
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/export/ tests/test_export_api.py -v`
Expected: PASS（含存量 docx/pdf/pptx 与 /api/export 契约测试）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/export/service.py tests/export/test_service.py
git commit -m "feat: [export] md 导出接入图片 base64 内嵌——产物自包含单文件"
```

---

### Task 3: 回归收口与验证

**Files:**
- Modify: `openspec/changes/update-report-export-md-images/tasks.md`（回填勾选）
- Test: 无新测试，跑存量全量

**Interfaces:**
- Consumes: Task 1/2 完成后的代码
- Produces: 验证证据（命令输出 + 人工抽查报告）

- [ ] **Step 1: Lint 与类型检查**

Run: `uv run ruff check && uv run mypy`
Expected: 0 errors（如有行超长，对 Task 1 Step 3 的 `out_lines.append(...)` 行按 ruff 提示换行）

- [ ] **Step 2: 全量后端测试**

Run: `uv run pytest`
Expected: 0 failed（前置条件：Langfuse/Docker 在线——全量套件依赖，见 AGENTS.md 测试约束）

- [ ] **Step 3: 人工抽查（红线：测试全过 ≠ 行为正确）**

用真实管线或 `export_report` 手工跑一份含图报告的 md 导出，本地渲染器（VS Code 预览/Typora）打开确认：图片可见、文件可单独拷走、无死链。结论按模板落 `tests/validation/2026-10-02-update-report-export-md-images-validation.md`（记录：文件大小、图片数、渲染结果）。

- [ ] **Step 4: 回填 openspec tasks.md 并准备收尾**

勾选 `openspec/changes/update-report-export-md-images/tasks.md` 全部项；走 finishing-a-development-branch 流程出 PR（origin/main 禁直推）。
