# ── 后端镜像：Python 3.12 + pip ─────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# 设置时区为中国标准时间（解决容器内时间与宿主机不匹配问题）
ENV TZ=Asia/Shanghai
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 国内 PyPI 镜像
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 先拷依赖清单（利用 Docker 层缓存）
COPY requirements.txt ./
COPY README.md ./

# 安装运行时依赖（排除 -e . 行，项目本身稍后安装）
RUN sed '/^-e \./d' requirements.txt > /tmp/reqs.txt && \
    pip install --no-cache-dir -r /tmp/reqs.txt

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
