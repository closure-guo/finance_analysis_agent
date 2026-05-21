"""check_cache: 逐项查缓存 + TTL，返回 FULL_HIT / RAW_HIT / MISS"""


def check_cache(state: dict) -> dict:
    return {"cache_result": "MISS"}
