# Navio Changelog

## [1.0.0] — 2026-08-10

### 🚀 首个正式版：金融多 Agent 智能咨询系统

经过完整的架构设计、核心模块开发与全栈联调，Navio 1.0 正式发布。本版本完成了一套基于 LLM 的金融产品咨询多 Agent 系统的基础设施搭建，覆盖理财、基金、存款、贷款、信用卡等核心业务场景。

---

### 🧠 多 Agent 编排与智能路由

- 实现三 Agent 架构：**GeneralAgent**（综合金融顾问）、**TechnicalAgent**（系统技术支持）、**BillingAgent**（账户与费用专员）
- 基于意图识别的自动路由：用户消息 → 意图识别 → 路由决策 → Agent 执行
- 支持多 Agent 并行协作（`run_parallel`），对复杂/跨领域问题同时咨询多个 Agent
- 路由质量反馈闭环：Monitor 监控 Agent 在线表现 → 自动调整路由权重 → 降低异常 Agent 优先级
- Agent 统计系统：实时追踪各 Agent 的总请求数、成功率、平均耗时、路由评分

### 🎯 15 种金融意图识别

- **三源融合投票机制**：LLM 语义识别 + Pattern 规则匹配 + Embedding 向量相似度，三路并行后加权投票
- 完整意图体系：
  - 理财/基金/存款：`financial_product`、`fund`、`deposit` → general
  - 贷款/信用卡/还款/费用：`loan`、`credit_card`、`repayment`、`fee_dispute` → billing
  - 紧急场景：`card_loss`（强制升级转人工）、`kyc`（开户实名）→ billing
  - 投资相关：`risk_assessment`、`investment_advice` → general（合规拦截）
  - 技术故障：`technical_login`、`technical_crash` → technical
  - 其他：`human_handoff`、`greeting`
- 意图识别缓存机制（TTL 5 分钟），减少 LLM 重复调用
- 实体提取：从用户消息中自动识别金额、产品名、期限等关键信息

### 🛡️ 合规红线

- 禁止荐股推荐：包含"推荐""该买吗""现在投合适吗"的请求自动拦截
- 禁止承诺收益：回复自动附加风险提示
- 强制风险提示：理财/基金回答末尾标配"投资有风险，过往业绩不预示未来表现"
- 挂失盗刷自动转人工：`card_loss` 意图识别后立即标记 `escalated=true`，引导拨打客服热线
- 禁止索要密码/验证码：Skill 规范中明确禁止事项

### 📚 RAG 金融知识库

- 基于 **ChromaDB** 的向量检索知识库
- 文档管理：支持单篇添加（`/knowledge/add`）和批量文件上传（`/knowledge/upload`）
- 语义检索：`/search` 接口返回 top-k 最相关文档片段及相似度分数
- **查询改写**：原始 query → LLM 改写为多角度检索词 → 提升召回率
- **结果重排**：检索结果通过 LLM 二次排序，优化相关性
- 长文档自动切片（500 字/片），保留语义完整性
- 默认内置客服场景知识文档（退款、订单、账户安全等）
- 知识库与对话记忆使用不同的 ChromaDB collection，互不干扰

### 💾 三级记忆架构

- **工作记忆（Redis）**：当前会话最近 N 条消息，毫秒级读写，24h TTL
- **情景记忆（ChromaDB episodic）**：跨会话历史对话片段，按语义相似度检索
- **用户画像（ChromaDB user_profile）**：从对话中 LLM 提炼的偏好和实体
- **智能压缩**：工作记忆超过 15 条时自动触发 LLM 摘要生成，压缩后保留摘要 + 最近 5 条原文
- 上下文构建时三级记忆融合，按重要性 + 时效性排序传给 Agent
- ChromaDB 优先连接独立服务（Docker Compose 模式），连不上自动降级为本地嵌入式

### 📋 Skills 热加载系统

- 三套完整的金融业务 Skills：
  - **综合金融咨询规范**：理财/基金/存款的咨询话术、回复结构、禁止事项
  - **金融系统技术支持规范**：网银/App 故障排查标准流程（网络→版本→权限→配置）
  - **账户与费用服务规范**：贷款/信用卡/还款/挂失/KYC 的完整场景规范
- `SKILL.md` 即改即生效：通过 `/skills/reload` 接口运行时热更新，无需重启服务
- Keywords 命中机制：根据用户消息关键词精确匹配适用的 Skill
- Agent 绑定：每个 Skill 可指定适用的 Agent 类型
- Front matter 元数据：无需 PyYAML 依赖的轻量级 YAML 解析

### 📊 在线监控

- **性能监控器**（`PerformanceMonitor`）：每隔 10 秒采集 Agent 和工具的运行统计
- **异常检测**：基于滑动窗口 Z-score 的统计异常检测（窗口 60 点，灵敏度 2.5）
- **告警系统**：成功率 / 延迟 / 熔断状态超阈值自动告警，支持 Webhook 推送
- **路由反馈闭环**：Monitor → Orchestrator 路由惩罚 → 自动降低异常 Agent 优先级
- **Prometheus 指标**：`agent_success_rate`、`agent_latency_ms`、`tool_success_rate`、`requests_total` 四个核心指标
- `/monitor` API：实时查看 Agent 统计、工具统计、活跃告警、优化建议

### 🧪 端到端评测

- **LLM-as-Judge** 评测框架：使用 LLM 对系统响应进行多维度打分
- **意图准确率评测**：给定消息 + 期望意图，评估 `intent_recognizer` 的识别准确率
- **对话质量评测**：从 relevance（相关性）、accuracy（准确性）、completeness（完整性）、helpfulness（帮助性）四个维度打分
- **回归检测**：与基线结果对比，自动发现质量退步
- **优化建议生成**：基于评测结果自动生成可操作的改进建议
- `/eval/run` API：一键运行评测并获取完整报告

### 🔧 工具管理（MCP）

- **MCPToolManager**：统一的工具注册、调用、统计框架
- **熔断器**（CircuitBreaker）：连续失败 5 次自动熔断，冷却 30 秒后尝试恢复
- **参数校验**：工具调用前自动校验必需参数
- **结果缓存**：基于查询文本的哈希缓存，TTL 5 分钟
- 内置 `knowledge_search` 工具：连接 RAG 知识库进行语义检索

### 🖥️ 前端调试控制台

- 基于 **Vue 3** + **Vite** 的单页应用
- 功能模块：
  - 对话调试：发送消息、查看意图、Agent 类型、响应时延、升级标记
  - 知识库检索：实时搜索知识库、查看相似度和来源
  - 知识库导入：批量添加文档、文件上传
- 后端状态面板：健康检查、知识片段数量、多个后端切换
- 支持 `conv_id` 自定义和自动生成

### 🐳 容器化部署

- **Docker Compose 五服务编排**（根目录单一 compose，一键启动）：
  - `navio-app`（FastAPI 主应用：8000）
  - `navio-frontend`（前端 Nginx：5174，托管 UI + `/api/python` API 反代）
  - `navio-chromadb`（向量数据库：8001）
  - `navio-redis`（工作记忆：6379）
  - `navio-prometheus`（监控：9090）
- 前端多阶段构建（Node 构建 → Nginx 托管），无需手动 `npm run build`
- 统一入口：前端 Nginx 同时承载静态页面与 API 反代，后端 API 可直连 `:8000`
- 数据持久化：Redis / ChromaDB / Prometheus 使用命名卷，Skills 目录保留 bind mount 支持热加载
- `.env` 配置驱动（根目录 `.env.template`），支持 Anthropic 官方及兼容协议（如 DeepSeek）的 LLM API
- `deploy.sh` 一键管理：up / down / restart / rebuild / status / logs / health / clean

### 📡 API 接口

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 健康检查 + Agent/技能摘要 |
| `/chat` | POST | 主对话接口 |
| `/search` | POST | 知识库语义检索 |
| `/knowledge/add` | POST | 批量添加知识文档 |
| `/knowledge/upload` | POST | 上传文件导入知识库 |
| `/knowledge/stats` | GET | 知识库统计 |
| `/monitor` | GET | 在线监控摘要 |
| `/metrics` | GET | Prometheus 指标 |
| `/skills` | GET | Skills 列表 |
| `/skills/reload` | POST | 热加载 Skills |
| `/eval/run` | POST | 运行端到端评测 |

### 📄 文档

- 项目 README：架构概述、快速开始、使用示例
- 后端 README（[Navio/README.md](Navio/README.md)）：全栈部署指南、接口文档、常见问题排障、ChromaDB/Redis 数据查看
- 优化蓝图（[BLUEPRINT.md](BLUEPRINT.md)）：v1.0 架构基线 + 四阶段演进路线

---

### 📦 技术栈

- **后端**：Python 3.11+ / FastAPI / Uvicorn / Anthropic SDK
- **存储**：Redis（工作记忆）/ ChromaDB（向量库 + 情景记忆 + 用户画像）
- **监控**：Prometheus + 自研 AnomalyDetector（Z-score）
- **前端**：Vue 3 / Vite
- **部署**：Docker / Docker Compose / Nginx
