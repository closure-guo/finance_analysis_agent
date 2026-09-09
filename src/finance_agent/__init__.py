# finance_agent 包级配置。
#
# pandas 3.x 兼容（2026-09-08 复盘）：pandas 3.0 默认开启 future.infer_string
# （pyarrow 字符串后端），akshare 1.18.94（PyPI 最新版，无升级通道）的正则处理
# 在 pyarrow 字符串上系统性崩溃（ArrowInvalid: invalid escape sequence: \u），
# 导致 stock_news_em（东财个股新闻）等数据源确定性失败——舆情感知数据缺失。
# 包级导入即关闭，恢复 akshare 数据源可用性（含测试进程，任何 finance_agent
# 子模块导入都会先执行本文件）。
import pandas as _pd

_pd.options.future.infer_string = False
