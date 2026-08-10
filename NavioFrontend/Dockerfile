# Navio 前端 — 多阶段构建
# 阶段 1：Node 构建静态资源；阶段 2：Nginx 托管 + API 反代

# ── 阶段 1：构建 ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# 先复制依赖清单，利用 Docker 层缓存（package-lock.json 不变时不重装依赖）
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# API 前缀在构建期注入；默认 /api/python，由容器内 Nginx 反代到后端
ARG VITE_PYTHON_API_URL=/api/python
ENV VITE_PYTHON_API_URL=$VITE_PYTHON_API_URL

RUN npm run build

# ── 阶段 2：运行（Nginx）──────────────────────────────────────────────────────
FROM nginx:1.27-alpine

LABEL org.opencontainers.image.title="navio-frontend" \
      org.opencontainers.image.description="Navio 前端控制台" \
      org.opencontainers.image.version="1.0.0"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
