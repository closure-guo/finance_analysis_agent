"""Web search tool — Tavily API wrapper for quick mode single tool call."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel


class SearchResult(BaseModel):
    """Single web search result."""

    title: str
    url: str
    content: str  # snippet/summary


class SearchResponse(BaseModel):
    """Complete search response."""

    query: str
    results: list[SearchResult]
    count: int
    answer: str | None = None  # Tavily AI 生成的实时摘要


# ── Tool definition for LLM function calling ──

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索网络获取实时信息。当用户询问任何需要最新数据的问题时调用，包括但不限于：天气、新闻、股票、体育赛事、科技动态等。宁可多搜也不要用过时知识回答。每次最多返回5条结果。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
            },
            "required": ["query"],
        },
    },
}


def tavily_search(query: str, max_results: int = 5) -> SearchResponse:
    """Execute Tavily web search.

    Args:
        query: Search query string
        max_results: Max number of results (default 5)

    Returns:
        SearchResponse with results

    Raises:
        ValueError: If TAVILY_API_KEY not set
        RuntimeError: If Tavily API call fails
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not configured")

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth="basic",
        include_answer=True,
    )

    results: list[SearchResult] = []
    for r in response.get("results", []):
        results.append(
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
            )
        )

    answer = response.get("answer") or None

    return SearchResponse(query=query, results=results, count=len(results), answer=answer)


def format_search_for_llm(response: SearchResponse) -> str:
    """Format search results as tool result string for LLM context.

    Format:
    [AI 摘要] {answer}    （如果 Tavily 返回了实时摘要）

    [1] {title}
    {url}
    {content}

    [2] {title}
    ...
    """
    lines: list[str] = []
    if response.answer:
        lines.append("[AI 摘要]")
        lines.append(response.answer)
        lines.append("")
    for i, r in enumerate(response.results, 1):
        lines.append(f"[{i}] {r.title}")
        lines.append(r.url)
        lines.append(r.content)
        lines.append("")
    return "\n".join(lines)


def has_tavily_key() -> bool:
    """Check if Tavily API key is configured."""
    return bool(os.environ.get("TAVILY_API_KEY", ""))


def parse_search_output(text: str) -> list[SearchResult]:
    """从 format_search_for_llm 的输出文本中解析结构化搜索结果。

    用于在前端展示搜索来源链接，无需重复调用 Tavily API。
    """
    results: list[SearchResult] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("[") and "]" in line:
            title = line.split("]", 1)[1].strip()
            url = lines[i + 1].strip() if i + 1 < len(lines) else ""
            content_lines: list[str] = []
            j = i + 2
            while j < len(lines) and lines[j].strip():
                content_lines.append(lines[j].strip())
                j += 1
            if url and url.startswith("http"):
                results.append(SearchResult(title=title, url=url, content=" ".join(content_lines)))
            i = j
        else:
            i += 1
    return results
