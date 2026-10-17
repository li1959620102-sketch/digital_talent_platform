# AI数字化人才平台 - Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 仅安装运行期依赖；Python 包均使用预编译 wheel，不在生产镜像中保留编译器。
# APT 源可切换：默认保持官方源（不改变原有行为），国内部署通过
# --build-arg APT_MIRROR=https://mirrors.aliyun.com 走镜像加速。
# 实测（2026-10-17 阿里云 ECS）：到 deb.debian.org 仅 77KB/s，
# 阿里云镜像 557KB/s，差距 7 倍；tesseract 的系统包较大，不换源会让构建拖到十几分钟。
ARG APT_MIRROR=http://deb.debian.org
RUN sed -i "s|http://deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|http://|https://|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y \
    --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

# 依赖源：默认官方 PyPI（生产保持原行为）。国内网络无法直连 pypi.org 时，
# 可通过 --build-arg PIP_INDEX_URL=<国内镜像> 指定，例如清华镜像。
ARG PIP_INDEX_URL=https://pypi.org/simple

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --retries 8 --timeout 180 -i ${PIP_INDEX_URL} -r requirements.txt

# 复制应用代码
COPY . .

# 使用非 root 用户运行应用，降低容器逃逸后的权限风险
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup appuser \
    && mkdir -p logs media \
    && chown -R appuser:appgroup /app

USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
