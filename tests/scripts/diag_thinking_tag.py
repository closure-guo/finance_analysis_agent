"""验证 <thinking> 标签是否触发 _safe_think_len 的 DSML 误拦截导致内容丢失。"""

from finance_agent.harness.loop import _DSML_DETECT, _safe_think_len

# DeepSeek 系统提示要求用 <thinking> 标签展示推理（loop.py:192）。
# 若模型在 content 里输出 <thinking>，_safe_think_len 是否误拦截？

cases = [
    "第一段\n1. 列表项A\n2. 列表项B\n第二段",
    "分析如下\n<thinking>这是思考</thinking>\n1. 列表A\n2. 列表B",
    "根据行情\n1. 中大\n2. 卧龙\n回复序号",
]

for text in cases:
    print("=" * 50)
    print("输入:", repr(text))
    # 模拟流式：逐段累积，每段调 _safe_think_len
    streamed = 0
    chunks = [text[i : i + 7] for i in range(0, len(text), 7)]  # 模拟小 token
    accumulated = ""
    out = ""
    for c in chunks:
        accumulated += c
        safe_end, dsml_found = _safe_think_len(accumulated, streamed)
        if safe_end > streamed:
            out += accumulated[streamed:safe_end]
        streamed = safe_end
        if dsml_found:
            print("  DSML 检出，停止流式 at", safe_end)
            break
    print("流式输出:", repr(out))
    print("完整一致:", out == text)
    print("DSML_DETECT 匹配:", bool(_DSML_DETECT.search(text)))
