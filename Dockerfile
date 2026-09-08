# ── 后端镜像：Python 3.12 + pip ─────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# 设置时区为中国标准时间（解决容器内时间与宿主机不匹配问题）
# fonts-noto-cjk：matplotlib 图表渲染中文所需（slim 基础镜像不含任何 CJK 字体，
# 缺失时中文全部渲染为豆腐块，且 matplotlib 仅静默回退 DejaVu Sans 无报错）
ENV TZ=Asia/Shanghai
# 先把 apt 源换成清华镜像（与 PIP_INDEX_URL 同思路），否则国内拉 deb.debian.org
# 只有几十 kB/s，安装 fonts-noto-cjk（56MB）会卡几十分钟
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends tzdata fonts-noto-cjk \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 国内 PyPI 镜像（2026-09-03 由清华 tuna 换阿里云：清华对大型 wheel 限流，
# 实测 17MB 的 litellm 只有 ~47kB/s；阿里云一般更稳）
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 先拷依赖清单（利用 Docker 层缓存）
COPY requirements.txt ./
COPY README.md ./

# 安装运行时依赖（排除 -e . 行，项目本身稍后安装）。
# --timeout/--retries：镜像限流或瞬时断连时 pip 自动重试，避免无限挂起
RUN sed '/^-e \./d' requirements.txt > /tmp/reqs.txt && \
    pip install --no-cache-dir --timeout 60 --retries 5 -r /tmp/reqs.txt

# 拷贝源码
COPY src ./src
COPY pyproject.toml ./

# 安装当前项目 + fastapi/uvicorn
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir fastapi "uvicorn[standard]"

# 运行时环境
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "finance_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
