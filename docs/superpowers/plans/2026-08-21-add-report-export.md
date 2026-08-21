# Add Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户通过右侧可开可关的「全部文件」抽屉，对当前或任意历史会话按需导出 PDF / Word / Markdown 三种格式（每次一个文件），并支持先预览后下载。

**Architecture:** 后端新增 WeasyPrint PDF 导出器 + 可复用导出服务 `export_report`（docx/pptx/pdf/md 四格式、统一免责声明、图片缺失容错），`generate_file` 改调该服务使 `file_paths` 扩展为四键；新增 `POST /api/export` 按需导出接口（从会话 `report_markdown` 现场生成单文件）。前端用 `ReportFileDrawer` 抽屉组件（默认关闭、两个打开入口、文件列表/预览/格式下载），`ReportCard` 的 Word/PPT 硬编码按钮替换为「全部文件」横幅。

**Tech Stack:** 后端 Python 3.12 + WeasyPrint（HTML→PDF）+ FastAPI；前端 React 18 + Vite + react-markdown + Tailwind；测试 pytest + vitest(@testing-library) + Playwright(stub 套件)。

## Global Constraints

- 单格式失败置 `null`，不阻断其余格式与管线（`nodes/output.py` 现行为：try/except 后 `docx_path = None`）
- `file_paths` 契约键：`docx` / `pptx` / `pdf` / `md`，值为完整文件路径或 `None`
- 所有格式文件必须追加免责声明（现有 `_DISCLAIMER` 文案，避免重复：先检查 `"免责声明" in text`）
- 文件名沿用 `{stock_code}_{YYYYmmdd_HHMMSS}_report.{ext}`（`datetime.now().strftime("%Y%m%d_%H%M%S")`）
- 图片缺失容错：转换前删除 markdown 中 `![alt](路径)` 且路径不存在的行（`re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$")` 逐行匹配）
- WeasyPrint 导入必须**惰性**（函数内 `from weasyprint import HTML`），系统库缺失时单格式失败置 `null`，不得中断 `generate_file` 或 `/api/export`
- 后端测试命名：`tests/test_*.py`（接口级）/ `tests/export/test_*.py`（导出器级）；E2E spec 放 `tests/e2e/playwright/tests/`
- E2E 反对 mock 被测系统（不 route.fulfill 业务接口）；selector 来自真实 DOM 快照（data-testid 优先）

---

### Task 1: 依赖与基础设施（weasyprint + 系统库）

**Files:**
- Modify: `pyproject.toml`（`[project] dependencies` 增 `weasyprint`）
- Modify: `requirements.txt`（由 `uv export` 重新生成）
- Modify: `Dockerfile`（apt 增 WeasyPrint 系统库）
- Modify: `.github/workflows/ci.yml`、`.github/workflows/e2e-playwright.yml`（单测 job / stub job 的 apt 增系统库）

**Interfaces:**
- Produces: 环境具备 `import weasyprint` 能力（Linux/CI/Docker）；Windows 本地缺 GTK 时惰性导入仍可 fail，由 pytest.importorskip 跳过 PDF 用例

- [ ] **Step 1: 在 pyproject.toml 增加依赖**

```toml
"weasyprint>=62.0",
```

- [ ] **Step 2: 更新锁文件并重新生成 requirements.txt**

Run:
```bash
uv lock
uv export --no-dev --format requirements-txt -o requirements.txt
```
Expected: uv.lock 出现 weasyprint 条目；requirements.txt 出现 `weasyprint==...` 与其 hashes；`git diff --stat` 显示两文件变更

- [ ] **Step 3: Dockerfile apt 增系统库**

在现有 `apt-get install ... tzdata fonts-noto-cjk` 一行追加（保留清华镜像源逻辑）：

```dockerfile
apt-get install -y --no-install-recommends tzdata fonts-noto-cjk \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info
```

- [ ] **Step 4: CI workflow apt 增系统库**

`ci.yml` 单测 job 与 `e2e-playwright.yml` stub job 的 apt 步骤（前者先加；e2e 已有 `fonts-noto-cjk` 安装步骤，追加相同三个 lib）：

```bash
sudo apt-get install -y -qq libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info
```

- [ ] **Step 5: 验证环境**

Run: `uv run python -c "from weasyprint import HTML; print('ok')"`
Expected: Linux/CI 打印 `ok`；Windows 本地允许 import 失败（后续 PDF 测试经 importorskip 跳过）

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements.txt Dockerfile .github/workflows/ci.yml .github/workflows/e2e-playwright.yml
git commit -m "chore(export): 引入 weasyprint 依赖与系统库（PDF 导出基础设施）"
```

---

### Task 2: PDF 导出器 `markdown_to_pdf`

**Files:**
- Create: `src/finance_agent/export/pdf_exporter.py`
- Test: `tests/export/test_pdf.py`

**Interfaces:**
- Consumes: `src/finance_agent/export/parser.py` 的 `parse_markdown` / `Section`（type∈heading/paragraph/table/separator/image）
- Produces: `markdown_to_pdf(markdown_text: str, output_path: str, stock_name: str = "") -> str`（返回 `output_path`，与 docx/pptx 签名一致）

- [ ] **Step 1: 写失败测试**

```python
"""export/pdf_exporter.py 单元测试。"""

import re
from pathlib import Path

import pytest

weasyprint = pytest.importorskip("weasyprint")

from finance_agent.export.pdf_exporter import markdown_to_pdf  # noqa: E402


def test_pdf_generation_with_chinese_and_table(tmp_path):
    markdown = (
        "# 测试报告\n\n"
        "## 第一章\n\n"
        "这是**中文**段落。\n\n"
        "| 指标 | 数值 |\n"
        "|------|------|\n"
        "| 营收 | 100亿 |\n"
    )
    output = tmp_path / "test.pdf"
    result = markdown_to_pdf(markdown, str(output), "测试股票")

    assert result == str(output)
    assert output.exists()
    assert output.stat().st_size > 0
    with output.open("rb") as f:
        assert f.read(5) == b"%PDF-"


def test_pdf_embeds_existing_image(tmp_path):
    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    markdown = f"# 报告\n\n![盈利图]({img})\n\n正文。\n"
    output = tmp_path / "with_img.pdf"

    markdown_to_pdf(markdown, str(output))

    assert output.exists()
    assert output.stat().st_size > 0


def test_pdf_skips_missing_image(tmp_path):
    markdown = "# 报告\n\n![图表](C:/不存在/图表.png)\n\n正文仍要渲染。\n"
    output = tmp_path / "no_img.pdf"

    result = markdown_to_pdf(markdown, str(output))

    assert result == str(output)
    assert output.exists()
    assert output.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/export/test_pdf.py -v`
Expected: FAIL（ImportError: No module named 'finance_agent.export.pdf_exporter'）

- [ ] **Step 3: 写最小实现 `markdown_to_pdf`**

```python
"""Markdown → PDF (.pdf) converter，基于 WeasyPrint（HTML → PDF）。

WeasyPrint 系统库（pango/cairo）缺失时惰性导入失败，由调用方容错（置 None）。
"""

from __future__ import annotations

from pathlib import Path

from finance_agent.export.parser import parse_markdown

_CSS = """
@page {
    size: A4;
    margin: 2cm 1.8cm;
    @bottom-center { content: counter(page) " / " counter(pages); font-size: 8pt; color: #888; }
}
body {
    font-family: "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 10.5pt; line-height: 1.6; color: #1a1a1a;
}
h1 { font-size: 20pt; text-align: center; margin: 0 0 12pt; }
h2 { font-size: 14pt; border-bottom: 1px solid #ddd; padding-bottom: 4pt; margin: 16pt 0 8pt; }
h3 { font-size: 12pt; margin: 12pt 0 6pt; }
p { margin: 6pt 0; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; }
th, td { border: 1px solid #999; padding: 4pt 8pt; font-size: 9.5pt; text-align: left; }
th { background: #f0f0f0; }
img { max-width: 100%; display: block; margin: 8pt auto; }
hr { border: none; border-top: 1px solid #ccc; margin: 12pt 0; }
"""


def _sections_to_html(markdown_text: str) -> str:
    from html import escape

    parts: list[str] = []
    for sec in parse_markdown(markdown_text):
        if sec.type == "heading":
            parts.append(f"<h{min(sec.level, 6)}>{escape(sec.text)}</h{min(sec.level, 6)}>")
        elif sec.type == "paragraph":
            parts.append(f"<p>{escape(sec.text)}</p>")
        elif sec.type == "table":
            rows_html = []
            for i, row in enumerate(sec.rows):
                tag = "th" if i == 0 else "td"
                cells = "".join(f"<{tag}>{escape(c)}</{tag}>" for c in row)
                rows_html.append(f"<tr>{cells}</tr>")
            parts.append(f"<table>{''.join(rows_html)}</table>")
        elif sec.type == "separator":
            parts.append("<hr/>")
        elif sec.type == "image":
            path = Path(sec.image_path)
            if path.exists():
                parts.append(f'<img src="{path.resolve().as_uri()}" alt="{escape(sec.text)}"/>')
    return "\n".join(parts)


def markdown_to_pdf(markdown_text: str, output_path: str, stock_name: str = "") -> str:
    """Convert markdown report to PDF document.

    Parameters
    ----------
    markdown_text : str
        Full markdown report.
    output_path : str
        Destination file path.
    stock_name : str
        Stock name（当前仅占位，标题沿用 markdown 自带 H1）.

    Returns
    -------
    str
        The output_path.
    """
    from weasyprint import HTML  # 惰性导入：系统库缺失时抛 ImportError，由调用方容错

    body = _sections_to_html(markdown_text)
    html = f"<html><head><meta charset='utf-8'/><style>{_CSS}</style></head><body>{body}</body></html>"
    HTML(string=html).write_pdf(output_path)
    return output_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/export/test_pdf.py -v`
Expected: PASS（3 passed；Windows 缺系统库时显示 1 skipped + 说明，属环境限制，CI 全量覆盖）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/export/pdf_exporter.py tests/export/test_pdf.py
git commit -m "feat(export): WeasyPrint 服务端 PDF 导出器（中文/表格/图片嵌入，缺失图跳过）"
```

---

### Task 3: 可复用导出服务 `export_report`

**Files:**
- Create: `src/finance_agent/export/service.py`
- Test: `tests/export/test_service.py`

**Interfaces:**
- Consumes: `markdown_to_docx` / `markdown_to_pptx` / `markdown_to_pdf`（三个签名一致：`(markdown_text, output_path, stock_name) -> str`）
- Produces:
  - `EXPORT_FORMATS: tuple[str, ...] == ("docx", "pptx", "pdf", "md")`
  - `sanitize_missing_images(markdown_text: str) -> str`（删除引用不存在文件的 `![alt](path)` 行）
  - `append_disclaimer(markdown_text: str) -> str`（含 `_DISCLAIMER` 文案；已含「免责声明」则不重复追加）
  - `export_report(markdown_text: str, stock_code: str, stock_name: str = "", formats: Sequence[str] = EXPORT_FORMATS) -> dict[str, str | None]`（写文件到 `REPORTS_DIR`，返回 `{fmt: 完整路径 | None}`；单格式失败置 None 不抛异常）

- [ ] **Step 1: 写失败测试**

```python
"""export/service.py 单元测试。"""

import os
from pathlib import Path

from finance_agent.export.service import append_disclaimer, export_report, sanitize_missing_images

_SAMPLE = "# 测试报告\n\n## 章节\n\n正文内容。\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"


def test_sanitize_missing_images_drops_broken_lines():
    text = "# 标题\n\n![好图](C:/存在/图.png)\n\n![坏图](C:/不存在/图.png)\n正文\n"
    result = sanitize_missing_images(text)

    assert "![好图]" in result
    assert "![坏图]" not in result
    assert "正文" in result


def test_append_disclaimer_idempotent():
    once = append_disclaimer("正文")
    twice = append_disclaimer(once)

    assert "免责声明" in once
    assert twice == once


def test_export_report_all_formats(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "贵州茅台")

    assert set(result.keys()) == {"docx", "pptx", "pdf", "md"}
    for fmt, path in result.items():
        assert path is not None, f"{fmt} 应生成成功"
        assert Path(path).exists()


def test_export_report_single_format(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    result = export_report(_SAMPLE, "600519", "贵州茅台", formats=("md",))

    assert list(result.keys()) == ["md"]
    assert result["md"] is not None
    content = Path(result["md"]).read_text(encoding="utf-8")
    assert "免责声明" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/export/test_service.py -v`
Expected: FAIL（ModuleNotFoundError: finance_agent.export.service）

- [ ] **Step 3: 写最小实现**

```python
"""可复用报告导出服务：Markdown → docx/pptx/pdf/md 四格式。

generate_file（管线结束自动生成）与 POST /api/export（按需导出）共用本模块，
统一负责免责声明追加、缺失图片图片容错与 REPORTS_DIR 落盘。
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from finance_agent.export.docx_exporter import markdown_to_docx
from finance_agent.export.pdf_exporter import markdown_to_pdf
from finance_agent.export.pptx_exporter import markdown_to_pptx

EXPORT_FORMATS: tuple[str, ...] = ("docx", "pptx", "pdf", "md")

_DISCLAIMER = (
    "\n\n---\n\n**免责声明**：本报告由 AI 系统基于公开财务数据自动生成，仅供参考，不构成任何投资建议。"
    "报告中的分析和结论基于历史数据和公开市场信息，不保证未来表现。"
    "投资者应结合自身情况独立判断，并咨询专业投资顾问。"
)

_IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")


def sanitize_missing_images(markdown_text: str) -> str:
    """删除引用不存在文件的图片行（![alt](path)），其余原样保留。"""
    out_lines = []
    for line in markdown_text.splitlines():
        m = _IMAGE_LINE_RE.match(line.strip())
        if m and not Path(m.group(2)).exists():
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def append_disclaimer(markdown_text: str) -> str:
    """追加统一免责声明（已含「免责声明」则不重复）。"""
    if "免责声明" in markdown_text:
        return markdown_text
    return markdown_text + _DISCLAIMER


def export_report(
    markdown_text: str,
    stock_code: str,
    stock_name: str = "",
    formats: Sequence[str] = EXPORT_FORMATS,
) -> dict[str, str | None]:
    """将报告 Markdown 生成指定格式文件到 REPORTS_DIR。

    Returns
    -------
    dict[str, str | None]
        {fmt: 完整文件路径 | None}，单格式失败置 None（不抛异常，不阻断其余格式）。
    """
    if not markdown_text:
        return {fmt: None for fmt in formats}

    markdown_text = append_disclaimer(sanitize_missing_images(markdown_text))

    reports_dir = Path(os.environ.get("REPORTS_DIR", "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = str(reports_dir / f"{stock_code}_{date_str}_report")

    converters = {
        "docx": (markdown_to_docx, ".docx"),
        "pptx": (markdown_to_pptx, ".pptx"),
        "pdf": (markdown_to_pdf, ".pdf"),
        "md": (None, ".md"),
    }

    result: dict[str, str | None] = {}
    for fmt in formats:
        if fmt not in converters:
            result[fmt] = None
            continue
        converter, ext = converters[fmt]
        target = base_name + ext
        try:
            if converter is None:  # md：直接写文本
                Path(target).write_text(markdown_text, encoding="utf-8")
            else:
                converter(markdown_text, target, stock_name)
            result[fmt] = target
        except Exception:
            result[fmt] = None  # noqa: S110 — 单格式失败容错
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/export/test_service.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/export/service.py tests/export/test_service.py
git commit -m "feat(export): 可复用导出服务 export_report（四格式/免责声明/缺失图容错）"
```

---

### Task 4: `generate_file` 改造为调用导出服务

**Files:**
- Modify: `src/finance_agent/nodes/output.py`
- Test: `tests/test_reports_dir_isolation.py`、`tests/test_graph_5layer.py`（回归）

**Interfaces:**
- Consumes: `export_report`（Task 3）
- Produces: `generate_file(state) -> dict`，返回键不变（`file_path`、`file_paths`、`final_report`），其中 `file_paths` 现在含四键 `docx/pptx/pdf/md`（值为完整路径或 None），**行为与旧版兼容**（旧契约 `dict[str, str | None]`，前端按 key 存在性判断）

- [ ] **Step 1: 写失败测试（新契约断言）**

在 `tests/test_graph_5layer.py` 内新增（或新建 `tests/test_generate_file_contract.py`）：

```python
"""nodes/output.generate_file 契约测试：file_paths 含四键，单格式失败置 None。"""

import os
from unittest.mock import patch

from finance_agent.nodes.output import generate_file


def test_generate_file_returns_four_format_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    state = {
        "final_report": "# 测试\n\n正文。\n",
        "stock_code": "600519",
        "stock_quote": {"name": "贵州茅台"},
    }

    result = generate_file(state)

    assert set(result["file_paths"].keys()) == {"docx", "pptx", "pdf", "md"}
    assert result["final_report"].count("免责声明") >= 1


def test_generate_file_single_failure_keeps_others(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    state = {
        "final_report": "# 测试\n\n正文。\n",
        "stock_code": "600519",
        "stock_quote": {"name": "贵州茅台"},
    }

    with patch(
        "finance_agent.export.service.markdown_to_pdf",
        side_effect=RuntimeError("render failed"),
    ):
        result = generate_file(state)

    assert result["file_paths"]["pdf"] is None
    assert result["file_paths"]["docx"] is not None
    assert result["file_paths"]["md"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_generate_file_contract.py -v`
Expected: FAIL（file_paths 只有 docx/pptx 键）

- [ ] **Step 3: 改造 `generate_file`**

重写 `src/finance_agent/nodes/output.py` 为：

```python
"""generate_file: 生成 Word/PPT/PDF/Markdown 文件（统一追加免责声明）。"""

from __future__ import annotations

from finance_agent.export.service import export_report


def generate_file(state: dict) -> dict:
    final_report = state.get("final_report", "")
    if not final_report:
        return {"file_path": None, "file_paths": None}

    stock_code = state.get("stock_code", "unknown")
    stock_name = _get_stock_name(state)

    # 导出服务统一处理免责声明、缺失图片容错、REPORTS_DIR 落盘与单格式失败容错
    file_paths = export_report(final_report, stock_code, stock_name)

    return {
        "file_path": file_paths.get("docx"),
        "file_paths": file_paths,
        "final_report": final_report,
    }


def _get_stock_name(state: dict) -> str:
    quote = state.get("stock_quote") or {}
    info = state.get("industry_info") or {}
    return str(quote.get("name") or info.get("name", ""))
```

> 注意：旧实现将免责声明并入 `final_report` 再写会话；新实现在服务内追加但返回的 `final_report` 不含免责声明。若发现现有断言依赖「会话报告含免责声明」，则在 `generate_file` 中改为 `final_report = append_disclaimer(final_report)` 后再返回，并补一条断言。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_generate_file_contract.py tests/test_reports_dir_isolation.py tests/test_graph_5layer.py -v`
Expected: PASS（新增全绿 + 既有回归不破）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/output.py tests/test_generate_file_contract.py
git commit -m "feat(export): generate_file 接入导出服务，file_paths 扩展四格式契约"
```

---

### Task 5: 按需导出接口 `POST /api/export`

**Files:**
- Modify: `src/finance_agent/api.py`
- Test: `tests/test_export_api.py`

**Interfaces:**
- Consumes: `get_session`（`session_store`，返回 dict 含 `report_markdown`/`stock_code`/`stock_name` 或 None）、`export_report`
- Produces: `POST /api/export`，请求体 `{session_id: str, fmt: "pdf"|"word"|"markdown"}`；响应 200 `{file_name, url: "/api/files/<name>"}`；404 会话不存在/无报告；400 格式非法；500 转换失败

- [ ] **Step 1: 写失败测试**

```python
"""POST /api/export 按需导出接口测试。"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from finance_agent.api import app


def _make_session(session_id: str, report_md: str) -> None:
    from finance_agent.session_store import create_session

    create_session(
        stock_code="600519",
        stock_name="贵州茅台",
        report_markdown=report_md,
    )


def test_export_pdf_returns_url(tmp_path, monkeypatch):
    import uuid

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    _make_session(uuid.uuid4().hex[:12], "# 测试报告\n\n正文。\n")
    # 从数据库取回真实 session_id
    from finance_agent.session_store import get_session, list_sessions

    session = list_sessions()[0]
    sid = session["session_id"]

    with TestClient(app) as client:
        resp = client.post("/api/export", json={"session_id": sid, "fmt": "pdf"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["file_name"].endswith(".pdf")
    assert data["url"].startswith("/api/files/")


def test_export_word_and_markdown(tmp_path, monkeypatch):
    from finance_agent.session_store import list_sessions

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    _make_session("unit-session-export-01", "# R\n\n正文。\n")

    with TestClient(app) as client:
        resp_word = client.post("/api/export", json={"session_id": "unit-session-export-01", "fmt": "word"})
        resp_md = client.post("/api/export", json={"session_id": "unit-session-export-01", "fmt": "markdown"})

    assert resp_word.status_code == 200
    assert resp_word.json()["file_name"].endswith(".docx")
    assert resp_md.status_code == 200
    assert resp_md.json()["file_name"].endswith(".md")


def test_export_unknown_session_404(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.post("/api/export", json={"session_id": "no-such-session", "fmt": "pdf"})

    assert resp.status_code == 404


def test_export_invalid_format_400(tmp_path, monkeypatch):
    from finance_agent.session_store import list_sessions

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    _make_session("unit-session-export-02", "# R\n")
    sid = list_sessions()[0]["session_id"]

    with TestClient(app) as client:
        resp = client.post("/api/export", json={"session_id": sid, "fmt": "exe"})

    assert resp.status_code == 400


def test_export_conversion_failure_500(tmp_path, monkeypatch):
    from finance_agent.session_store import list_sessions

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    _make_session("unit-session-export-03", "# R\n正文。\n")
    sid = list_sessions()[0]["session_id"]

    with (
        patch("finance_agent.export.service.markdown_to_pdf", side_effect=RuntimeError("boom")),
        TestClient(app) as client,
    ):
        resp = client.post("/api/export", json={"session_id": sid, "fmt": "pdf"})

    assert resp.status_code == 500
```

> 注：`list_sessions` 若不存在于 session_store，改用 `get_session` 直查已知 session_id（测试内 `_make_session` 用固定 id 便于直查）。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export_api.py -v`
Expected: FAIL（404/无路由）

- [ ] **Step 3: 实现接口**

在 `api.py` 的 `download_file`（约 1868 行）前后新增：

```python
class ExportRequest(BaseModel):
    session_id: str
    fmt: str  # pdf | word | markdown（映射 docx/md）


_FMT_TO_KEY = {"pdf": "pdf", "word": "docx", "markdown": "md"}


@app.post("/api/export")
async def export_report_file(req: ExportRequest):
    """按需导出：从会话 report_markdown 现场生成单一文件，返回可下载 URL。"""
    import asyncio

    from finance_agent.export.service import export_report as do_export
    from finance_agent.session_store import get_session

    fmt_key = _FMT_TO_KEY.get(req.fmt)
    if fmt_key is None:
        raise HTTPException(status_code=400, detail="不支持的导出格式，可选：pdf / word / markdown")

    session = await asyncio.to_thread(get_session, req.session_id)
    report_md = (session or {}).get("report_markdown") or ""
    if not report_md:
        raise HTTPException(status_code=404, detail="会话不存在或无报告内容")

    stock_code = (session or {}).get("stock_code") or "unknown"
    stock_name = (session or {}).get("stock_name") or ""

    # 转换在独立线程执行，避免阻塞事件循环（现有 API 同款模式）
    result = await asyncio.to_thread(do_export, report_md, stock_code, stock_name, (fmt_key,))
    path = result.get(fmt_key)

    if not path:
        raise HTTPException(status_code=500, detail="报告导出失败，请稍后重试")

    file_name = str(Path(path).name)
    return {"file_name": file_name, "url": f"/api/files/{file_name}"}
```

（确保 `Path` 已 import；`BaseModel`、`HTTPException`、`app` 均已存在。若 `ExportRequest` 需与既有 Pydantic 风格一致，把 class 放到文件顶部其他 Request class 旁。）

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_export_api.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/test_export_api.py
git commit -m "feat(api): 新增 POST /api/export 按需导出（pdf/word/markdown，404/400/500）"
```

---

### Task 6: 前端 `ReportFileDrawer` 抽屉组件

**Files:**
- Create: `frontend/src/ReportFileDrawer.tsx`
- Test: `frontend/src/test/reportFileDrawer.test.tsx`

**Interfaces:**
- Consumes: `UIMessage`（`filePaths?: Record<string,string>`、`reportMarkdown?`、`sessionId?`）
- Produces: `ReportFileDrawer({ drawerMessage, onClose })`；内部状态 `view: 'list' | 'preview'`；导出格式元数据 `EXPORT_FORMATS = [{key:'pdf',label:'PDF',icon:'fa-file-pdf'},{key:'docx',label:'Word',icon:'fa-file-word'},{key:'md',label:'Markdown',icon:'fa-file-code'}]`；导出文件展示时补充 `pptx`（如有）仅列出不强制
- 下载逻辑：`filePaths[key]` 存在 → `<a href="/api/files/<basename>" download>`；不存在 → `POST /api/export {session_id, fmt}` → 用返回的 `url` 触发下载

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ReportFileDrawer } from '../ReportFileDrawer'
import type { UIMessage } from '../types'

const baseMsg: UIMessage = {
  id: 'm1',
  type: 'report',
  content: '',
  reportMarkdown: '# 测试报告\n\n## 章节\n\n正文内容。\n\n| A | B |\n|---|---|\n| 1 | 2 |\n',
  sessionId: 's1',
  filePaths: { docx: '/tmp/600519_x_report.docx', pdf: '/tmp/600519_x_report.pdf' },
}

describe('ReportFileDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('默认关闭：不渲染内容；点击全部文件横幅后才打开（由父组件控制）', () => {
    const { container } = render(<ReportFileDrawer drawerMessage={null} onClose={() => {}} />)
    expect(container.querySelector('[data-testid="export-drawer"]')).toBeNull()
  })

  it('打开后展示文件列表（含格式徽标）', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    expect(screen.getByTestId('export-drawer')).toBeTruthy()
    expect(screen.getByText('PDF')).toBeTruthy()
    expect(screen.getByText('Word')).toBeTruthy()
    const md = screen.queryByText('Markdown')
    // md/docx 无 filePaths 键时仍以导出动作列出（可现场生成）
    expect(md).toBeTruthy()
  })

  it('点击关闭按钮 / Esc / 遮罩可关闭', () => {
    const onClose = vi.fn()
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('drawer-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('已有文件直接给下载链接', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    const pdfLink = screen.getByTestId('download-pdf')
    expect(pdfLink.getAttribute('href')).toBe('/api/files/600519_x_report.pdf')
  })

  it('缺失文件先 POST /api/export 再下载', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ file_name: '600519_y_report.md', url: '/api/files/600519_y_report.md' }),
    }) as unknown as typeof fetch
    render(<ReportFileDrawer drawerMessage={{ ...baseMsg, filePaths: { docx: '/tmp/a.docx' } }} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('download-md'))
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/api/export', expect.objectContaining({ method: 'POST' }))
    })
  })

  it('预览面板渲染 Markdown 正文', () => {
    render(<ReportFileDrawer drawerMessage={baseMsg} onClose={() => {}} />)
    fireEvent.click(screen.getByTestId('preview-open'))
    expect(screen.getByTestId('drawer-preview')).toBeTruthy()
    expect(screen.getByText('测试报告')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/test/reportFileDrawer.test.tsx`
Expected: FAIL（Cannot find module '../ReportFileDrawer'）

- [ ] **Step 3: 实现组件**

```tsx
import { useCallback, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { UIMessage } from './types'

export interface ExportFormatMeta {
  key: string
  label: string
  icon: string
  apiFmt: string // POST /api/export 的 fmt 值
}

// 导出菜单：PDF / Word / Markdown（pptx 仅当 filePaths 存在时展示，不强制）
export const EXPORT_FORMATS: ExportFormatMeta[] = [
  { key: 'pdf', label: 'PDF', icon: 'fa-file-pdf', apiFmt: 'pdf' },
  { key: 'docx', label: 'Word', icon: 'fa-file-word', apiFmt: 'word' },
  { key: 'md', label: 'Markdown', icon: 'fa-file-code', apiFmt: 'markdown' },
]

const basename = (p?: string) => (p ? String(p).split(/[\\/]/).pop() : '')

export function ReportFileDrawer({ drawerMessage, onClose }: {
  drawerMessage: UIMessage | null
  onClose: () => void
}) {
  const [view, setView] = useState<'list' | 'preview'>('list')

  // Esc 关闭
  useEffect(() => {
    if (!drawerMessage) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerMessage, onClose])

  const handleDownload = useCallback(async (fmt: ExportFormatMeta) => {
    if (!drawerMessage) return
    const existing = drawerMessage.filePaths?.[fmt.key]
    if (existing) {
      const a = document.createElement('a')
      a.href = `/api/files/${basename(existing)}`
      a.download = basename(existing)
      a.click()
      return
    }
    const resp = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: drawerMessage.sessionId, fmt: fmt.apiFmt }),
    })
    if (!resp.ok) return
    const data = await resp.json()
    const a = document.createElement('a')
    a.href = data.url
    a.download = data.file_name
    a.click()
  }, [drawerMessage])

  if (!drawerMessage) return null

  const fileList = [...EXPORT_FORMATS]
  if (drawerMessage.filePaths?.pptx) {
    fileList.push({ key: 'pptx', label: 'PPT', icon: 'fa-file-powerpoint', apiFmt: '' })
  }

  return (
    <div className="fixed inset-0 z-[60]" data-testid="export-drawer">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} data-testid="drawer-backdrop" />
      {/* 抽屉主体 */}
      <div className="absolute right-0 top-0 bottom-0 w-[420px] max-w-[90vw] flex flex-col"
        style={{ background: 'var(--bg-base)', borderLeft: '1px solid var(--border-neutral-l1)' }}>
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-neutral-l1)' }}>
          <span className="text-sm font-semibold" style={{ color: 'var(--text-default)' }}>全部文件</span>
          <button onClick={onClose} data-testid="drawer-close"
            className="text-[var(--icon-secondary)] hover:text-[var(--text-default)]">
            <i className="fas fa-times"></i>
          </button>
        </div>

        {view === 'list' ? (
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
            {fileList.map(fmt => (
              <div key={fmt.key} className="flex items-center gap-3 p-3 rounded-lg"
                style={{ background: 'var(--bg-base-secondary)' }}>
                <i className={`fas ${fmt.icon} text-sm`} style={{ color: 'var(--text-brand)' }}></i>
                <span className="flex-1 text-sm" style={{ color: 'var(--text-default)' }}>
                  报告.{fmt.key === 'docx' ? 'docx' : fmt.key === 'pdf' ? 'pdf' : fmt.key === 'md' ? 'md' : 'pptx'}
                </span>
                <button onClick={() => setView('preview')} data-testid="preview-open"
                  className="text-xs px-2 py-1 rounded" style={{ background: 'var(--bg-overlay-l1)' }}>
                  预览
                </button>
                {fmt.key !== 'pptx' && (
                  <button onClick={() => handleDownload(fmt)} data-testid={`download-${fmt.key}`}
                    className="text-xs px-2 py-1 rounded" style={{ background: 'var(--bg-brand-popup)', color: 'var(--text-brand)' }}>
                    <i className="fas fa-download mr-1"></i>下载
                  </button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-4 py-3" data-testid="drawer-preview" style={{ maxHeight: 'calc(100vh - 56px)' }}>
            <button onClick={() => setView('list')} className="text-xs mb-2" style={{ color: 'var(--text-brand)' }}>
              <i className="fas fa-arrow-left mr-1"></i>返回文件列表
            </button>
            <div className="prose prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}
                components={{ img: () => null, a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>
                {drawerMessage.reportMarkdown || ''}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/test/reportFileDrawer.test.tsx`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ReportFileDrawer.tsx frontend/src/test/reportFileDrawer.test.tsx
git commit -m "feat(frontend): 导出抽屉 ReportFileDrawer（列表/预览/按格式下载）"
```

---

### Task 7: `ReportCard` 集成「全部文件」横幅 + App 挂载抽屉

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ReportFileDrawer`（Task 6）、`UIMessage`
- Produces: App 内新增状态 `drawerMessage: UIMessage | null`；`ReportCard` 新增可选 prop `onOpenFiles: (msg: UIMessage) => void`；报告头部渲染「全部文件」横幅替代 Word/PPT 硬编码按钮；App 根节点挂载 `<ReportFileDrawer drawerMessage={drawerMessage} onClose={() => setDrawerMessage(null)} />`

- [ ] **Step 1: 写失败测试（ReportCard 横幅）**

```typescript
// frontend/src/test/reportCardExportBanner.test.tsx —— 与 Task 6 测试同批次文件目录
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
// 若 ReportCard 未导出，则通过最小化策略：测试经 App 级渲染（见说明）
```

> 实现取舍：`ReportCard` 是 App.tsx 内部函数未导出。以「横幅出现 + 点击回调触发」为验收，通过 `frontend/src/test/` 内对 App.tsx 的集成渲染验证，或把 `ReportCard` 提升导出。本任务以**人工 + E2E 验证为主**（任务卡见 Task 8），单元层由 Task 6 覆盖抽屉自身；此处写一条最小断言：报告消息渲染后存在「全部文件」文案按钮。

- [ ] **Step 2: 修改 `ReportCard` 函数签名与头部按钮**

在 `App.tsx`：

```tsx
function ReportCard({ msg, onOpenFiles }: { msg: UIMessage; onOpenFiles?: (msg: UIMessage) => void }) {
```

将头部右侧的 Word/PPT 两个 `<a>` 按钮（约 1598-1617 行）整体替换为：

```tsx
<div className="flex gap-2">
  <button
    onClick={() => onOpenFiles?.(msg)}
    data-testid="open-files-banner"
    className="h-8 px-3 rounded-lg flex items-center gap-1.5 text-xs font-medium transition-colors"
    title="查看并导出文件"
    style={{ background: 'var(--bg-base-secondary)', color: 'var(--icon-secondary)' }}
    onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-overlay-l1)' }}
    onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--bg-base-secondary)' }}
  >
    <i className="fas fa-folder-open text-xs"></i>
    <span>全部文件</span>
  </button>
</div>
```

- [ ] **Step 3: App 状态与挂载**

在 App 组件顶部加状态：

```tsx
const [drawerMessage, setDrawerMessage] = useState<UIMessage | null>(null)
```

在渲染一个 `ReportCard` 的位置（约 1243 行 `return <ReportCard msg={msg} />`）改为：

```tsx
return <ReportCard msg={msg} onOpenFiles={setDrawerMessage} />
```

在 App 根 return 的末尾（`</>` 前，SettingsModal 之后）挂载：

```tsx
{drawerMessage && (
  <ReportFileDrawer drawerMessage={drawerMessage} onClose={() => setDrawerMessage(null)} />
)}
```

并确认 `ReportFileDrawer` 已 import（`import { ReportFileDrawer } from './ReportFileDrawer'`）。

- [ ] **Step 4: 验证构建 + 相关测试**

Run:
```bash
cd frontend && npx tsc -b --noEmit && npx vitest run
```
Expected: PASS（类型检查通过、现有全部前端测试不破；Task 6 新增用例在内）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): ReportCard 接入全部文件横幅 + App 挂载导出抽屉"
```

---

### Task 8: E2E spec（抽屉交互 + 按需导出）

**Files:**
- Create: `tests/e2e/playwright/tests/report-export.spec.ts`

**Interfaces:**
- Consumes: 后端 `TESTING=1` stub 管线（产生 `report_ready` 带 `file_paths` 四键）、前端真实 DOM
- Produces: stub 套件下确定性通过的抽屉交互 spec

- [ ] **Step 1: 用 playwright-test-generator / 手动探索，抓取真实 DOM 快照**

启动 `TESTING=1` 后端 + 前端 dev，跑一次深度分析至报告就绪，记录：报告头部「全部文件」横幅的稳定定位（`data-testid="open-files-banner"`）、抽屉内格式行的 `data-testid`（`download-pdf` 等）、预览面板 `data-testid="drawer-preview"`。**selector 必须来自真实快照**，禁止盲写。

- [ ] **Step 2: 写失败 spec（stub 套件）**

```typescript
import { test, expect } from '@playwright/test'

test.describe('报告导出抽屉', () => {
  test('分析完成后可打开全部文件抽屉、预览并下载 PDF', async ({ page }) => {
    // 进入已有报告会话：引导流程与 streaming.spec 一致（输入股票码 → 深度分析 → 等待报告完成）
    await page.goto('/')
    // ...（按 streaming.spec.ts 的既有交互步骤：填输入框、发请求、等待 report_ready）
    // 断言稳定终态：报告头部出现「全部文件」横幅
    await expect(page.getByTestId('open-files-banner')).toBeVisible()

    // 打开抽屉
    await page.getByTestId('open-files-banner').click()
    await expect(page.getByTestId('export-drawer')).toBeVisible()

    // 文件列表含 PDF 下载项
    await expect(page.getByTestId('download-pdf')).toBeVisible()

    // 预览面板渲染正文
    await page.getByTestId('preview-open').click()
    await expect(page.getByTestId('drawer-preview')).toBeVisible()

    // 关闭抽屉（Esc 或关闭按钮）
    await page.getByTestId('drawer-close').click()
    await expect(page.getByTestId('export-drawer')).toBeHidden()
  })
})
```

> 备注：下载动作本身（`download-pdf` 触发浏览器下载）以 stub 环境 `file_paths` 是否携带 pdf 为准；若 stub 管线不产出 pdf，改为断言「有 file 时 href 正确 / 无 file 时点击触发 /api/export 请求」——**禁止用 route.fulfill/MSW 伪造接口响应**（AGENTS.md 红线）。

- [ ] **Step 3: scan.sh 快扫 + e2e-reviewer 深审**

Run: `bash .trae/skills/e2e-reviewer/scripts/scan.sh tests/e2e/playwright/tests/report-export.spec.ts`，按 e2e-reviewer 清单自查：恒真断言、缺 await、手动取值断言、条件绕过、waitForTimeout 赌时序——P0/P1 清零。

- [ ] **Step 4: 本地跑 stub 门禁**

Run: `cd tests/e2e/playwright && npx playwright test report-export.spec.ts`
Expected: PASS；随后全量 `npx playwright test` 回归不破。

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/playwright/tests/report-export.spec.ts
git commit -m "test(e2e): 报告导出抽屉交互 spec（打开/预览/关闭）"
```

---

## Self-Review

**Spec 覆盖对照（delta add-report-export）：**
- 按需导出接口（pdf/word/markdown、404/400/500、单文件）→ Task 5 ✅
- 服务端 PDF 生成（中文/表格/图片嵌入/缺失降级）→ Task 2 ✅
- `file_paths` 四键契约 + 单格式失败不阻断 → Task 3、Task 4 ✅
- 抽屉默认关闭/两入口/列表/预览/格式下载/关闭三方式/空态 → Task 6、Task 7 ✅（空态即 filePaths 为空时仍列出三格式走 /api/export，已覆盖）
- E2E spec → Task 8 ✅
- 人工验证报告 + 全量门禁 → 执行期收尾（tasks.md 兜底），不在计划内单列 ✅

**占位符扫描：** 无 TBD/TODO；Task 8 交互代码需按真实 DOM 快照落 selector（明确标注以 streaming.spec 为模板 + 红线约束），其余步骤均含完整代码。

**类型一致性：** `markdown_to_pdf(markdown_text, output_path, stock_name) -> str` 三任务间一致；`export_report(markdown_text, stock_code, stock_name, formats) -> dict[str,str|None]` 在 Task 3/4/5 签名一致；前端 `EXPORT_FORMATS` 的 `apiFmt` 与后端 `_FMT_TO_KEY` 键（pdf/word/markdown）对齐；`data-testid`（open-files-banner / export-drawer / drawer-close / drawer-preview / download-*）在 Task 6/7/8 一致。