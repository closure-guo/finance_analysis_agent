"""Web search tool - Tavily API wrapper for quick mode single tool call."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def batch_tavily_search(
    queries: list[str], max_results_per_query: int = 5, max_workers: int = 4
) -> list[SearchResponse]:
    """并行执行多个 Tavily 搜索查询，合并去重后返回。

    使用 ThreadPoolExecutor 并行调用 Tavily API，按 URL 去重。
    单个查询失败不影响其他查询。

    Args:
        queries: 搜索关键词列表
        max_results_per_query: 每个查询的最大结果数
        max_workers: 最大并行线程数

    Returns:
        去重后的 SearchResponse 列表（每个 query 一个，失败的 query 返回空结果）
    """
    if not has_tavily_key():
        raise ValueError("TAVILY_API_KEY not configured")

    if not queries:
        return []

    results_map: dict[int, SearchResponse] = {}

    def _single_search(idx: int, q: str) -> tuple[int, SearchResponse]:
        try:
            resp = tavily_search(q, max_results=max_results_per_query)
            return idx, resp
        except Exception:
            return idx, SearchResponse(query=q, results=[], count=0)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(queries))) as executor:
        futures = [executor.submit(_single_search, i, q) for i, q in enumerate(queries)]
        for future in as_completed(futures):
            idx, resp = future.result()
            results_map[idx] = resp

    responses = [results_map[i] for i in range(len(queries))]

    seen_urls: set[str] = set()
    for resp in responses:
        deduped: list[SearchResult] = []
        for r in resp.results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                deduped.append(r)
        resp.results = deduped
        resp.count = len(deduped)

    return responses


def format_batch_for_llm(responses: list[SearchResponse]) -> str:
    """将批量搜索结果格式化为 LLM 友好的文本。

    每个查询的结果连续编号，便于引用。
    """
    lines: list[str] = []
    ref_num = 0
    for resp in responses:
        if not resp.results:
            continue
        lines.append(f"## 搜索: {resp.query}")
        if resp.answer:
            lines.append(f"[AI 摘要] {resp.answer}")
            lines.append("")
        for r in resp.results:
            ref_num += 1
            lines.append(f"[{ref_num}] {r.title}")
            lines.append(r.url)
            lines.append(r.content)
            lines.append("")
    return "\n".join(lines)


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
