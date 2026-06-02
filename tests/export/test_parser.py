"""export/parser.py 单元测试。"""

from finance_agent.export.parser import Section, parse_markdown, split_by_chapters


def test_parse_heading():
    text = "# Title\n\n## Subtitle\n\n### Section"
    sections = parse_markdown(text)

    assert len(sections) == 3
    assert sections[0] == Section(type="heading", level=1, text="Title")
    assert sections[1] == Section(type="heading", level=2, text="Subtitle")
    assert sections[2] == Section(type="heading", level=3, text="Section")


def test_parse_table():
    text = "| A | B |\n|---|---|\n| 1 | 2 |"
    sections = parse_markdown(text)

    assert len(sections) == 1
    assert sections[0].type == "table"
    assert sections[0].rows == [["A", "B"], ["1", "2"]]


def test_parse_paragraph():
    text = "This is a paragraph.\n\nAnother paragraph."
    sections = parse_markdown(text)

    assert len(sections) == 2
    assert sections[0].type == "paragraph"
    assert "This is a paragraph." in sections[0].text
    assert sections[1].type == "paragraph"
    assert "Another paragraph." in sections[1].text


def test_parse_separator():
    text = "Line\n\n---\n\nAnother"
    sections = parse_markdown(text)

    types = [s.type for s in sections]
    assert "separator" in types


def test_split_by_chapters():
    sections = [
        Section(type="heading", level=2, text="Ch1"),
        Section(type="paragraph", text="p1"),
        Section(type="heading", level=2, text="Ch2"),
        Section(type="paragraph", text="p2"),
    ]
    chapters = split_by_chapters(sections)

    assert len(chapters) == 2
    assert chapters[0][0] == "Ch1"
    assert chapters[0][1][0].text == "p1"
    assert chapters[1][0] == "Ch2"
    assert chapters[1][1][0].text == "p2"
