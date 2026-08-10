# Navio 智能客服系统 — Docker 多阶段构建
# 目标：生产镜像精简、依赖缓存独立、非 root 运行
# 构建: docker build --target production -t navio:latest .

# ── 阶段 1：基础环境 ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# curl 用于健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── 阶段 2：依赖安装 + 模型预热（独立层，代码变更不触发重装）──────────────────
FROM base AS dependencies

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 预下载 ChromaDB 内置 ONNX embedding 模型（~79MB），避免运行时下载超时。
# 仅在 ChromaDB 服务不可用、降级为本地嵌入式模式时需要；提前缓存保证离线可启动。
RUN mkdir -p /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2 && \
    curl -L --retry 3 --retry-delay 5 -o /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx.tar.gz \
    https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz && \
    tar -xzf /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx.tar.gz -C \
    /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2 && \
    rm /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx.tar.gz

# ── 阶段 3：生产镜像 ──────────────────────────────────────────────────────────
FROM base AS production

LABEL org.opencontainers.image.title="navio" \
      org.opencontainers.image.description="Navio 金融多 Agent 智能咨询系统" \
      org.opencontainers.image.version="1.0.0"

# 非 root 用户运行
RUN useradd -m -u 1000 navio

# 从依赖阶段复制已安装的包（保留层缓存）
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin
# 预下载的 ONNX 模型缓存
COPY --from=dependencies --chown=navio:navio /root/.cache/chroma /home/navio/.cache/chroma

# 应用代码
COPY --chown=navio:navio . .

# 只调整运行期需要写入的目录权限
RUN mkdir -p /app/data/chroma /app/data/eval /app/logs && \
    chown -R navio:navio /app/data /app/logs

USER navio

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

# ── 阶段 4：开发镜像（热重载 + 调试）─────────────────────────────────────────
FROM dependencies AS development

COPY . .

RUN mkdir -p /app/data/chroma /app/data/eval /app/logs && \
    chmod -R 777 /app/data /app/logs

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
