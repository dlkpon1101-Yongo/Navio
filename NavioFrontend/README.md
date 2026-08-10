# Navio Frontend

独立 Vue 前端项目，连接 Navio Python 版本（FastAPI）后端。

## 功能

- 聊天调试：对话、意图识别、多 Agent 路由信息展示（intent / agent_type / RAG / 转人工）。
- 健康检查、监控摘要、知识库检索、知识库文档导入、文件上传。
- 支持 Docker + Nginx 部署。

## 默认后端地址

| 后端 | 默认地址 |
|------|----------|
| Python | `http://localhost:8000` |

开发模式下，Vite 会代理：

| 前端路径 | 代理到 |
|----------|--------|
| `/api/python` | `http://localhost:8000` |

Docker 模式下，Nginx 通过 `proxy_pass http://navio:8000/` 反代到同一 Compose 网络中的后端容器（见根目录 `docker-compose.yml`），无需 `host.docker.internal`。

## 本地运行

安装依赖：

```bash
npm install
```

启动：

```bash
npm run dev
```

访问：

```text
http://localhost:5173
```

如果后端端口不是默认值，可以启动时覆盖：

```bash
VITE_PYTHON_API_URL=http://localhost:8000 npm run dev
```

## Docker 部署

前端 Dockerfile 为多阶段构建（Node 构建 → Nginx 托管），无需手动 `npm run build`。

在**仓库根目录**构建并启动完整全栈（含后端与基础设施）：

```bash
docker compose up -d --build
```

访问：

```text
http://localhost:5174
```

停止：

```bash
docker compose down
```

## 后端启动参考

Python 版默认：

```text
http://localhost:8000
```
