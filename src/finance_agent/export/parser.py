"""Simple markdown parser for export converters.

Parses markdown text into structured Sections that can be consumed by
docx_exporter and pptx_exporter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Section:
    type: str  # "heading" | "paragraph" | "table" | "separator" | "image"
    level: int = 0
    text: str = ""
    rows: list[list[str]] = field(default_factory=list)
    image_path: str = ""


def parse_markdown(text: str) -> list[Section]:
    """Parse markdown text into a list of Sections."""
    lines = text.splitlines()
    sections: list[Section] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Separator
        if stripped == "---":
            sections.append(Section(type="separator"))
            i += 1
            continue

        # Heading
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            sections.append(Section(type="heading", level=level, text=heading_match.group(2)))
            i += 1
            continue

        # Image: ![alt](path)
        image_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if image_match:
            sections.append(
                Section(type="image", text=image_match.group(1), image_path=image_match.group(2))
            )
            i += 1
            continue

        # Table
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            rows = _parse_table_rows(table_lines)
            if rows:
                sections.append(Section(type="table", rows=rows))
            continue

        # Paragraph (skip empty lines)
        if stripped:
            para_lines = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip():
                para_lines.append(lines[i].strip())
                i += 1
            sections.append(Section(type="paragraph", text=" ".join(para_lines)))
            continue

        # Empty line
        i += 1

    return sections


def _parse_table_rows(lines: list[str]) -> list[list[str]]:
    """Parse markdown table lines into rows of cells."""
    rows = []
    for line in lines:
        # Skip separator rows like |---|---|
        if re.match(r"^\|(?:\s*[-:]+\s*\|)+$", line):
            continue
        # Split by | and strip
        cells = [cell.strip() for cell in line.split("|")]
        # Remove empty cells from leading/trailing |
        cells = [c for c in cells if c or c == "0"]
        if cells:
            rows.append(cells)
    return rows


def split_by_chapters(sections: list[Section]) -> list[tuple[str, list[Section]]]:
    """Split sections into chapters, where each chapter starts with a level-2 heading.

    Returns list of (chapter_title, chapter_sections).
    """
    chapters: list[tuple[str, list[Section]]] = []
    current_title = ""
    current_sections: list[Section] = []

    for sec in sections:
        if sec.type == "heading" and sec.level == 2:
            if current_sections or current_title:
                chapters.append((current_title, current_sections))
            current_title = sec.text
            current_sections = []
        else:
            current_sections.append(sec)

    if current_sections or current_title:
        chapters.append((current_title, current_sections))

    return chapters
