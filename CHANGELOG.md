# Changelog

## [0.3] — 2026-08-10 — 金融产品咨询 Agent

### 业务层
- **意图体系**：从电商 17 种意图重构为金融 15 种意图（`financial_product` `fund` `deposit` `loan` `credit_card` `repayment` `fee_dispute` `card_loss` `kyc` `risk_assessment` `investment_advice`）
- **Agent 角色**：`general` 改为综合金融顾问、`billing` 改为账户与费用专员，`technical` 改为金融系统技术支持
- **合规红线**：Agent system_prompt 内嵌禁荐股/禁承诺收益/强制风险提示/挂失盗刷自动转人工
- **Skills 替换**：3 套电商 Skills → 3 套金融 Skills（`financial_products` / `tech_support` / `account_services`）
- Pattern 关键词库全面金融化（理财/基金/存款/贷款/信用卡/挂失/开户…）
- RAG 触发白名单与业务关键词金融化
- 评测用例 11 条电商版 → 11 条金融版
- 前端占位文案金融化

### 技术层
- `core/intent_recognizer.py`：`IntentCategory` 枚举替换、`_TEMPLATES` Few-shot 替换、`_pattern_recognize` 关键词替换、`_INTENT_GROUPS` 替换
- `agents/agent_orchestrator.py`：`system_prompt` ×3 重写、`_INTENT_ROUTING` 重映射、`_domain_scores` 双阈值打分更新、`_collaboration_targets` 更新、`_needs_escalation` 金融关键词更新
- `api/main.py`：`_should_use_knowledge` 意图白名单更新
- `evaluation/evaluator.py`：`DEFAULT_INTENT_CASES` 替换
- `NavioFrontend/src/App.vue`：placeholder/search/doc 默认内容金融化

---

## [0.2] — 2026-08-10 — 前端纯 Python 重写

### 业务层
- 移除 Java 后端支持与切换 UI（`segmented` 按钮、Java API 输入框、`switchBackend` 逻辑）
- 品牌标识 `EM` → `NV`
- 主页链接从「小红书」改为「GitHub」

### 技术层
- `src/lib/backends.js` 重写为仅支持 Python（`conv_id` 语义），兼容旧 localStorage
- `src/App.vue`：模板与 `<script setup>` 重构
- `vite.config.js` / `docker/nginx.conf`：删除 `/api/java` 代理
- `agents/agent_orchestrator.py._call_llm`：增加 DeepSeek 空响应自动重试（解决约 25% 偶发空内容）
- `docker-compose.yml`/`config/nginx/nginx.conf`：修复 nginx IPv6 健康检查失败

---

## [0.1] — 2026-08-10 之前 — 电商客服（EchoMind rebrand → Navio）

### 业务层
- 基于 EchoMind 电商客服架构的初始 Navio 版本
- 三 Agent：general（通用客服）/ technical（技术支持）/ billing（账单服务）
- 意图体系：电商 17 种（order_status, logistics, refund, invoice, payment_issue, technical_login…）
- Skills：`general_customer_service` / `technical_support` / `billing_support`

### 技术层
- Python FastAPI 后端 + Vue 3 前端
- 多 Agent 路由（三层决策：意图路由 → 性能路由 → 降级路由）
- 意图识别三源融合（LLM + Pattern + Embedding）
- RAG 知识库（ChromaDB 向量检索 + 查询改写 + 重排）
- 三级记忆（Redis 工作记忆 + ChromaDB 情景记忆 + 用户画像）
- Skills 动态注入 / 热加载
- Docker Compose 全栈部署（app + redis + chromadb + nginx + prometheus）
- 前端支持 Python / Java 双后端切换
