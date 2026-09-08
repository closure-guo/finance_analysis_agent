"""pandas 3.x 与 akshare 兼容守卫（infer_string）。

pandas 3.0 默认开启 future.infer_string（pyarrow 字符串后端），akshare 1.18.94
（PyPI 最新版，无升级通道）的正则处理在 pyarrow 字符串上崩（ArrowInvalid:
invalid escape sequence: \\u），导致 stock_news_em 等数据源确定性失败（舆情缺失）。
finance_agent 包级导入 SHALL 关闭 infer_string 恢复 akshare 可用性。
"""


def test_infer_string_disabled_by_package_import():
    import pandas as pd

    import finance_agent  # noqa: F401  # 包级导入应关闭 infer_string

    assert pd.options.future.infer_string is False
