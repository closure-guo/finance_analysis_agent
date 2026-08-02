"""一次性重命名脚本：把 camelCase 函数名/参数名改为 snake_case（ruff N802/N803）。"""

from pathlib import Path

p = Path("src/finance_agent/api.py")
src = p.read_text(encoding="utf-8")

# (old, new) 对：函数名与参数名 snake_case 化（局部变量保持 camelCase）
pairs = [
    ("afterSeq: int = 0,", "after_seq: int = 0,"),
    ("onEvent: Any = None,", "on_event: Any = None,"),
    ("onEvent：yield 前对事件 dict 的就地修改回调", "on_event：yield 前对事件 dict 的就地修改回调"),
    ("if onEvent is not None:", "if on_event is not None:"),
    ("onEvent(ev)", "on_event(ev)"),
    ("async def _errGen()", "async def _err_gen()"),
    ("StreamingResponse(_errGen()", "StreamingResponse(_err_gen()"),
    ("displayName: str | None,", "display_name: str | None,"),
    ("apiKey: str | None,", "api_key: str | None,"),
    ("analysisId: str,", "analysis_id: str,"),
    ("startTime: float,", "start_time: float,"),
    ("if displayName is not None:", "if display_name is not None:"),
    ('"display_name": displayName,', '"display_name": display_name,'),
    (
        "mode=mode, api_key=apiKey, session_id=session_id",
        "mode=mode, api_key=api_key, session_id=session_id",
    ),
    ("api_key=apiKey,", "api_key=api_key,"),
    ("analysis_id=analysisId,", "analysis_id=analysis_id,"),
    ("(time.time() - startTime)", "(time.time() - start_time)"),
    ("def onMetadata(metadata: dict) -> None:", "def on_metadata_cb(metadata: dict) -> None:"),
    ("def onResolved(sc: str, sn: str) -> None:", "def on_resolved_cb(sc: str, sn: str) -> None:"),
    ("on_metadata=onMetadata,", "on_metadata=on_metadata_cb,"),
    ("on_resolved=onResolved,", "on_resolved=on_resolved_cb,"),
    ("def _enrichDone(ev: dict) -> None:", "def _enrich_done(ev: dict) -> None:"),
    ("onEvent=_enrichDone", "on_event=_enrich_done"),
]

missing = []
for old, new in pairs:
    if old in src:
        src = src.replace(old, new)
    else:
        missing.append(old[:60])

p.write_text(src, encoding="utf-8")
if missing:
    print("NOT FOUND:")
    for m in missing:
        print(f"  {m}")
else:
    print("all replaced")
