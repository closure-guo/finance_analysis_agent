"""Dataset 建库(spec Requirement「评估 Dataset 与覆盖矩阵」)。

幂等:以 (input.query, input.mode) 为去重键,已存在 item 跳过不覆盖。
langfuse 未配置时返回 error,不抛异常(CI/本地可无 langfuse 跑 --local)。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DATASET_NAME = "a-share-analysis-v1"
_ITEMS_PATH = Path(__file__).parent / "dataset_items.json"


def load_items(path: Path | None = None) -> list[dict]:
    """读取 dataset items(seed 与 --local 实验共用的 source of truth)。"""
    items: list[dict] = json.loads((path or _ITEMS_PATH).read_text(encoding="utf-8"))
    return items


def seed(client=None) -> dict:
    """幂等建库。返回 {created, skipped, error}。"""
    if client is None:
        from finance_agent.langfuse_tracing import get_langfuse

        client = get_langfuse()
    if client is None:
        return {"created": 0, "skipped": 0, "error": "langfuse 未配置,跳过 seed"}
    items = load_items()
    existing: set = set()
    try:
        dataset = client.get_dataset(DATASET_NAME)
        existing = {(it.input.get("query"), it.input.get("mode")) for it in dataset.items}
    except Exception as e:
        # 过宽兜底:网络抖动/认证过期等异常也会落到此分支。
        # 记 warning 以便排查被吞掉的异常,再尝试 create_dataset。
        logger.warning("get_dataset(%s) 失败,尝试 create_dataset: %s", DATASET_NAME, e)
        client.create_dataset(
            name=DATASET_NAME,
            description="A 股分析评估 Dataset v1(覆盖矩阵:deep 典型/边界、quick、follow_up、意图澄清)",
            metadata={"version": "v1"},
        )
        # create_dataset 返回原始 Dataset API 类型(无 .items);新建库必为空,
        # existing 保持空集即可,勿迭代其返回值。
    created = skipped = 0
    for item in items:
        key = (item["input"]["query"], item["input"]["mode"])
        if key in existing:
            skipped += 1
            continue
        client.create_dataset_item(
            dataset_name=DATASET_NAME,
            input=item["input"],
            expected_output=item.get("expected_output"),
            metadata=item.get("metadata"),
        )
        created += 1
    client.flush()
    return {"created": created, "skipped": skipped, "error": None}


if __name__ == "__main__":
    # 与 api.py 一致：CLI 入口加载 .env（否则 shell 无 LANGFUSE/LLM key，误判「未配置」）
    from dotenv import load_dotenv

    load_dotenv()
    print(seed())
