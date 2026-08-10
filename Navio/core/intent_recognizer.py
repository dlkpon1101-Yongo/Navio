"""
亮点：端到端意图识别

三路融合策略：
  1. LLM 语义理解（权重 70%）—— 主力，理解复杂语义和上下文
  2. Embedding 向量相似度（权重 20%）—— 快速匹配常见表达
  3. 关键词模式匹配（权重 10%）—— 零延迟兜底

三路结果通过加权投票合并，置信度低于阈值时降级为 OTHER。
LLM 和 Embedding 并行调用，不串行等待。
"""
import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic

from core.llm_utils import extract_text_content

logger = logging.getLogger(__name__)


class IntentCategory(Enum):
    # ── 金融业务意图 ──────────────────────────────────────────────────
    FINANCIAL_PRODUCT = "financial_product"   # 理财产品查询
    FUND              = "fund"                # 基金查询
    DEPOSIT           = "deposit"             # 存款查询
    LOAN              = "loan"                # 贷款查询
    CREDIT_CARD       = "credit_card"         # 信用卡查询
    REPAYMENT         = "repayment"           # 还款查询
    FEE_DISPUTE       = "fee_dispute"         # 费用异议
    CARD_LOSS         = "card_loss"           # 挂失/盗刷
    KYC               = "kyc"                 # 开户/实名认证
    RISK_ASSESSMENT   = "risk_assessment"     # 风险评估
    INVESTMENT_ADVICE = "investment_advice"   # 投资建议
    # ── 通用意图 ────────────────────────────────────────────────────
    QUERY             = "query"               # 信息查询
    COMPLAINT         = "complaint"           # 投诉不满
    REQUEST           = "request"             # 请求操作
    GREETING          = "greeting"            # 问候
    ESCALATION        = "escalation"          # 要求升级
    FEEDBACK          = "feedback"            # 正面反馈
    # ── 系统技术意图 ────────────────────────────────────────────────
    TECHNICAL_LOGIN   = "technical_login"     # 登录认证故障
    TECHNICAL_CRASH   = "technical_crash"     # 崩溃/系统报错
    HUMAN_HANDOFF     = "human_handoff"       # 转人工
    OTHER             = "other"


class UrgencyLevel(Enum):
    LOW      = 1
    MEDIUM   = 2
    HIGH     = 3
    CRITICAL = 4


@dataclass
class IntentResult:
    intent:     IntentCategory
    confidence: float
    urgency:    UrgencyLevel
    intent_group: str
    entities:   Dict[str, List[str]]   # 从消息中提取的实体
    reasoning:  str
    latency_ms: float
    source_scores: Dict[str, float] = field(default_factory=dict)


# ── Few-shot 模板（同时用于 LLM 示例和 Embedding 匹配）────────────────────────
_TEMPLATES: Dict[IntentCategory, List[str]] = {
    # ── 金融业务 ───────────────────────────────────────────────────
    IntentCategory.FINANCIAL_PRODUCT: ["这款理财产品年化收益是多少？", "这个理财产品的风险等级是几级？", "有没有期限短的理财推荐？"],
    IntentCategory.FUND:              ["这只基金最近净值多少？", "申购费率怎么算？", "基金赎回几天到账？"],
    IntentCategory.DEPOSIT:           ["大额存单现在利率多少？", "定期存款和活期存款哪个划算？", "通知存款七天利率是多少？"],
    IntentCategory.LOAN:              ["信用贷利率多少？", "贷款额度怎么计算？", "装修贷最长能贷几年？"],
    IntentCategory.CREDIT_CARD:       ["我的信用卡账单能分期吗？", "信用卡年费可以免吗？", "信用卡临时额度怎么申请？"],
    IntentCategory.REPAYMENT:         ["这个月贷款要还多少？", "房贷提前还款有什么限制？", "逾期一天会怎么样？"],
    IntentCategory.FEE_DISPUTE:       ["这笔手续费为什么这么高？", "跨行转账收费多少？", "账户管理费怎么收取？"],
    IntentCategory.CARD_LOSS:         ["我的卡丢了怎么挂失？", "信用卡被盗刷了怎么办？", "挂失后多久能补新卡？"],
    IntentCategory.KYC:               ["怎么开通理财账户？", "实名认证需要什么材料？", "账户信息怎么修改？"],
    IntentCategory.RISK_ASSESSMENT:   ["我是稳健型适合买什么？", "风险等级怎么划分？", "风险评估问卷在哪里？"],
    IntentCategory.INVESTMENT_ADVICE: ["现在买这个基金合适吗？", "这个理财值得投吗？", "帮我推荐一只基金"],
    # ── 通用 ─────────────────────────────────────────────────────
    IntentCategory.QUERY:      ["怎么查我的贷款余额？", "在哪里看基金净值？", "账户明细在哪查？"],
    IntentCategory.COMPLAINT:  ["等了很久没人处理！", "服务太差了！", "这个手续费不合理！"],
    IntentCategory.REQUEST:    ["帮我修改账户信息", "我需要打印流水", "请帮我取消订阅"],
    IntentCategory.GREETING:   ["你好", "嗨，有人吗", "早上好"],
    IntentCategory.ESCALATION: ["我要投诉！", "转人工客服", "找你们经理"],
    IntentCategory.FEEDBACK:   ["服务很棒！", "非常满意", "给个好评"],
    # ── 技术 ─────────────────────────────────────────────────────
    IntentCategory.TECHNICAL_LOGIN: ["网银登录一直提示超时", "验证码收不到", "登录页面打不开"],
    IntentCategory.TECHNICAL_CRASH: ["转账页面报500错误", "App一直闪退", "系统提示服务不可用"],
    IntentCategory.HUMAN_HANDOFF:   ["转人工客服", "我要找人工", "请升级处理"],
}

_SPECIFIC_INTENTS = {
    IntentCategory.FINANCIAL_PRODUCT,
    IntentCategory.FUND,
    IntentCategory.DEPOSIT,
    IntentCategory.LOAN,
    IntentCategory.CREDIT_CARD,
    IntentCategory.REPAYMENT,
    IntentCategory.FEE_DISPUTE,
    IntentCategory.CARD_LOSS,
    IntentCategory.KYC,
    IntentCategory.RISK_ASSESSMENT,
    IntentCategory.INVESTMENT_ADVICE,
    IntentCategory.TECHNICAL_LOGIN,
    IntentCategory.TECHNICAL_CRASH,
    IntentCategory.HUMAN_HANDOFF,
}

_GENERIC_INTENTS = {
    IntentCategory.QUERY,
    IntentCategory.REQUEST,
    IntentCategory.COMPLAINT,
    IntentCategory.ESCALATION,
}

_INTENT_GROUPS: Dict[IntentCategory, IntentCategory] = {
    # 金融业务 → 查询/请求/投诉
    IntentCategory.FINANCIAL_PRODUCT: IntentCategory.QUERY,
    IntentCategory.FUND:              IntentCategory.QUERY,
    IntentCategory.DEPOSIT:           IntentCategory.QUERY,
    IntentCategory.RISK_ASSESSMENT:   IntentCategory.QUERY,
    IntentCategory.LOAN:              IntentCategory.REQUEST,
    IntentCategory.CREDIT_CARD:       IntentCategory.REQUEST,
    IntentCategory.REPAYMENT:         IntentCategory.REQUEST,
    IntentCategory.FEE_DISPUTE:       IntentCategory.COMPLAINT,
    IntentCategory.CARD_LOSS:         IntentCategory.COMPLAINT,
    IntentCategory.KYC:               IntentCategory.REQUEST,
    IntentCategory.INVESTMENT_ADVICE: IntentCategory.REQUEST,
    # 技术
    IntentCategory.TECHNICAL_LOGIN:   IntentCategory.QUERY,
    IntentCategory.TECHNICAL_CRASH:   IntentCategory.COMPLAINT,
    IntentCategory.HUMAN_HANDOFF:     IntentCategory.ESCALATION,
}

# 紧急关键词
_URGENCY_KEYWORDS = {
    UrgencyLevel.CRITICAL: ["紧急", "emergency", "urgent", "asap", "立刻", "盗刷", "被偷", "挂失", "冻结", "亏损"],
    UrgencyLevel.HIGH:     ["今天", "马上", "尽快", "hurry", "now", "逾期", "吞卡"],
    UrgencyLevel.MEDIUM:   ["这周", "soon", "快点"],
}


def _cosine(a: List[float], b: List[float]) -> float:
    """纯 Python 余弦相似度，不依赖 numpy。"""
    dot = sum(x * y for x, y in zip(a, b))
    na  = sum(x * x for x in a) ** 0.5
    nb  = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class IntentRecognizer:
    """
    端到端意图识别器。

    初始化时不加载任何本地模型，所有 AI 能力通过 Anthropic API 调用。
    模板 Embedding 在首次请求时懒加载并缓存，后续复用。
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
        confidence_threshold: float = 0.5,
    ):
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client    = AsyncAnthropic(**kwargs)
        self.model     = model
        self.threshold = confidence_threshold
        # 第三方兼容 API（如 DeepSeek）通常不支持 Embedding，禁用该策略。
        # 官方 Anthropic SDK 当前没有 embeddings 资源，因此下面会使用稳定的
        # 本地字符 n-gram 向量作为轻量兜底，保证三路融合链路真实可跑。
        self._embedding_enabled = not bool(base_url)

        self._tpl_embeddings: Dict[IntentCategory, List[List[float]]] = {}
        self._cache: Dict[str, IntentResult] = {}
        self.cache_hits   = 0
        self.cache_misses = 0

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    async def recognize(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> IntentResult:
        """
        识别用户意图。

        history 格式：[{"role": "user"/"assistant", "content": "..."}]
        """
        key = self._cache_key(message, history)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        self.cache_misses += 1

        t0 = time.monotonic()

        # LLM 和 Embedding 并行（Embedding 不可用时跳过）
        llm_task = asyncio.create_task(self._llm_recognize(message, history))
        emb_task = asyncio.create_task(self._embedding_recognize(message)) if self._embedding_enabled else None
        pat      = self._pattern_recognize(message)

        if emb_task:
            llm, emb = await asyncio.gather(llm_task, emb_task)
        else:
            llm = await llm_task
            emb = {"intent": IntentCategory.OTHER, "confidence": 0.0}

        intent, confidence, source_scores = self._vote(llm, emb, pat)
        entities = self._extract_entities(message)
        urgency  = self._urgency(message, intent)

        result = IntentResult(
            intent=intent,
            confidence=confidence,
            urgency=urgency,
            intent_group=self._intent_group(intent),
            entities=entities,
            reasoning=llm.get("reasoning", ""),
            latency_ms=(time.monotonic() - t0) * 1000,
            source_scores=source_scores,
        )

        # LRU 缓存
        if len(self._cache) >= 1000:
            for k in list(self._cache)[:500]:
                del self._cache[k]
        self._cache[key] = result
        return result

    def learn(self, message: str, correct: IntentCategory) -> None:
        """在线学习：将纠正样本加入模板，清除对应 Embedding 缓存。"""
        tpls = _TEMPLATES.setdefault(correct, [])
        if message not in tpls:
            tpls.append(message)
            self._tpl_embeddings.pop(correct, None)  # 下次重新计算
            logger.info(f"学习新样本 → {correct.value}: {message[:40]}")

    # ── 三路识别策略 ──────────────────────────────────────────────────────────

    async def _llm_recognize(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]],
    ) -> Dict[str, Any]:
        """策略 1：LLM 语义理解（Few-shot + 上下文）。"""
        message = self._clean_text(message)
        # 构建 Few-shot 示例
        examples = "\n".join(
            f'  消息: "{t}" → 意图: {cat.value}'
            for cat, tpls in _TEMPLATES.items()
            for t in tpls[:1]  # 每类取 1 条，控制 prompt 长度
        )
        # 最近 3 轮对话上下文
        ctx = ""
        if history:
            ctx = "\n最近对话:\n" + "\n".join(
                f"  {self._clean_text(m.get('role', 'user'))}: {self._clean_text(m.get('content', ''))}"
                for m in history[-3:]
            )

        prompt = f"""你是客服意图分析专家。根据示例判断用户意图，返回 JSON。
如果用户问题能匹配细粒度业务意图，请优先返回细粒度意图，而不是宽泛大类。
例如退款优先返回 refund，发票优先返回 invoice，登录故障优先返回 technical_login。

示例:
{examples}

{ctx}
用户消息: "{message}"

返回格式（仅 JSON，不要其他文字）:
{{"intent": "<意图值>", "confidence": <0-1>, "reasoning": "<一句话说明>"}}

可选意图: {", ".join(c.value for c in IntentCategory)}"""
        prompt = self._clean_text(prompt)

        try:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = extract_text_content(resp.content)
            s, e = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[s:e])
            try:
                data["intent"] = IntentCategory(data["intent"])
            except ValueError:
                data["intent"] = IntentCategory.OTHER
            return data
        except Exception as ex:
            logger.warning(f"LLM 识别失败: {ex}")
            return {"intent": IntentCategory.OTHER, "confidence": 0.0, "reasoning": "LLM 失败", "failed": True}

    async def _embedding_recognize(self, message: str) -> Dict[str, Any]:
        """策略 2：Embedding 向量相似度匹配。"""
        try:
            await self._load_template_embeddings()
            msg_vec = await self._embed_text(message)

            best_cat, best_score = IntentCategory.OTHER, 0.0
            for cat, vecs in self._tpl_embeddings.items():
                score = max(_cosine(msg_vec, v) for v in vecs)
                if score > best_score:
                    best_score, best_cat = score, cat

            return {"intent": best_cat, "confidence": best_score}
        except Exception as ex:
            logger.warning(f"Embedding 识别失败: {ex}")
            return {"intent": IntentCategory.OTHER, "confidence": 0.0}

    def _pattern_recognize(self, message: str) -> Dict[str, Any]:
        """策略 3：关键词模式匹配（同步，零延迟兜底）。"""
        msg = message.lower()
        specific_patterns = {
            IntentCategory.HUMAN_HANDOFF:  ["转人工", "人工客服", "找人工"],
            IntentCategory.FINANCIAL_PRODUCT: ["理财", "年化", "固收", "净值型", "结构性"],
            IntentCategory.FUND:           ["基金", "申购", "赎回", "净值", "etf"],
            IntentCategory.DEPOSIT:        ["存款", "存单", "定期", "活期", "通知存款"],
            IntentCategory.LOAN:           ["贷款", "利率", "额度", "抵押", "信用贷", "装修贷"],
            IntentCategory.CREDIT_CARD:    ["信用卡", "账单", "分期", "额度", "年费", "积分"],
            IntentCategory.REPAYMENT:      ["还款", "提前还款", "月供", "逾期", "宽限期"],
            IntentCategory.FEE_DISPUTE:    ["手续费", "管理费", "扣费", "收费", "转账费"],
            IntentCategory.CARD_LOSS:      ["挂失", "盗刷", "被偷", "丢了", "失卡"],
            IntentCategory.KYC:            ["开户", "实名", "认证", "身份证", "人脸"],
            IntentCategory.RISK_ASSESSMENT: ["风险等级", "风险测评", "保守", "稳健", "风险承受"],
            IntentCategory.INVESTMENT_ADVICE: ["推荐", "值得投", "适合买", "哪个好", "建议"],
            IntentCategory.TECHNICAL_LOGIN:  ["无法登录", "登录失败", "401", "验证码", "超时"],
            IntentCategory.TECHNICAL_CRASH:  ["崩溃", "闪退", "500", "报错", "crash", "服务不可用"],
        }
        generic_patterns = {
            IntentCategory.ESCALATION: ["投诉", "经理", "supervisor"],
            IntentCategory.COMPLAINT:  ["太差", "糟糕", "horrible"],
            IntentCategory.QUERY:      ["?", "？", "怎么", "什么", "哪里", "查"],
            IntentCategory.REQUEST:    ["帮我", "需要", "please", "help", "申请"],
            IntentCategory.GREETING:   ["你好", "嗨", "hello", "hi"],
        }

        best_cat, best_score = self._best_pattern_match(msg, specific_patterns)
        if best_cat != IntentCategory.OTHER:
            return {"intent": best_cat, "confidence": best_score}

        best_cat, best_score = self._best_pattern_match(msg, generic_patterns)
        return {"intent": best_cat, "confidence": best_score}

    # ── 投票合并 ──────────────────────────────────────────────────────────────

    def _vote(self, llm: Dict, emb: Dict, pat: Dict) -> tuple[IntentCategory, float, Dict[str, float]]:
        """加权投票。返回最终意图、融合置信度和各路来源得分。"""
        source_scores = {
            "llm": float(llm.get("confidence", 0.0) or 0.0),
            "embedding": float(emb.get("confidence", 0.0) or 0.0),
            "pattern": float(pat.get("confidence", 0.0) or 0.0),
        }
        if llm.get("failed"):
            if emb.get("intent") != IntentCategory.OTHER and emb.get("confidence", 0.0) > 0:
                return emb["intent"], source_scores["embedding"], source_scores
            if pat.get("intent") != IntentCategory.OTHER and pat.get("confidence", 0.0) > 0:
                return pat["intent"], source_scores["pattern"], source_scores
            return IntentCategory.OTHER, 0.0, source_scores

        if self._embedding_enabled:
            weights = [(llm, 0.7), (emb, 0.2), (pat, 0.1)]
        else:
            weights = [(llm, 0.85), (pat, 0.15)]
        scores: Dict[IntentCategory, float] = {}
        for result, w in weights:
            cat  = result.get("intent", IntentCategory.OTHER)
            conf = result.get("confidence", 0.0)
            scores[cat] = scores.get(cat, 0.0) + w * conf

        best = max(scores, key=scores.get)  # type: ignore
        best_score = scores[best]
        pat_intent = pat.get("intent", IntentCategory.OTHER)
        pat_conf = float(pat.get("confidence", 0.0) or 0.0)
        if best in _GENERIC_INTENTS and pat_intent in _SPECIFIC_INTENTS and pat_conf >= 0.5 and best_score < 0.8:
            source_scores["refined_by_pattern"] = pat_conf
            return pat_intent, max(best_score, pat_conf), source_scores
        if best_score < self.threshold:
            return IntentCategory.OTHER, best_score, source_scores
        return best, best_score, source_scores

    # ── 实体提取 ──────────────────────────────────────────────────────────────

    def _extract_entities(self, message: str) -> Dict[str, List[str]]:
        """用规则提取高价值实体，避免每次识别都额外调用 LLM。"""
        message = self._clean_text(message)
        return {
            "order_id": self._unique(re.findall(r"(?:订单号?|order(?:_id)?|#)\s*[:：#]?\s*([A-Za-z0-9_-]{4,32})", message, re.I)),
            "product": [],
            "date": self._unique(re.findall(r"(今天|明天|昨天|本周|这周|下周|\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)", message)),
            "amount": self._unique(re.findall(r"((?:¥|￥)\s*\d+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?\s*(?:元|块|rmb|cny|usd|美元))", message, re.I)),
            "error_code": self._unique(re.findall(r"\b([45]\d{2}|[A-Z][A-Z0-9_-]{2,16})\b", message)),
        }

    # ── 辅助 ──────────────────────────────────────────────────────────────────

    async def _load_template_embeddings(self) -> None:
        """懒加载所有模板的 Embedding（只在首次调用时执行）。"""
        missing = [cat for cat in _TEMPLATES if cat not in self._tpl_embeddings]
        if not missing:
            return

        all_texts = [t for cat in missing for t in _TEMPLATES[cat]]
        vecs = [await self._embed_text(text) for text in all_texts]
        idx = 0
        for cat in missing:
            n = len(_TEMPLATES[cat])
            self._tpl_embeddings[cat] = vecs[idx: idx + n]
            idx += n

    async def _embed_text(self, text: str) -> List[float]:
        """
        生成文本向量。

        如果未来接入的官方/兼容客户端提供 embeddings.create，会优先使用远端向量；
        当前 Anthropic SDK 没有该资源时，退化为字符 n-gram 哈希向量。这样不会因为
        Embedding 服务缺失导致三路融合中断。
        """
        embeddings = getattr(self.client, "embeddings", None)
        if embeddings is not None:
            try:
                resp = await embeddings.create(model="voyage-3-lite", input=[text])
                return list(resp.data[0].embedding)
            except Exception as ex:
                logger.warning(f"远端 Embedding 失败，使用本地向量兜底: {ex}")

        return self._local_embedding(text)

    @staticmethod
    def _local_embedding(text: str, dims: int = 256) -> List[float]:
        """稳定的字符 n-gram 哈希向量，用于无远端 Embedding 时的语义近似匹配。"""
        normalized = text.lower().strip()
        vec = [0.0] * dims
        tokens = set()
        for n in (1, 2, 3):
            if len(normalized) >= n:
                tokens.update(normalized[i:i + n] for i in range(len(normalized) - n + 1))
        if not tokens:
            tokens.add(normalized)

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        return vec

    def _urgency(self, message: str, intent: IntentCategory) -> UrgencyLevel:
        msg = message.lower()
        for level, kws in _URGENCY_KEYWORDS.items():
            if any(kw in msg for kw in kws):
                return level
        if intent in (IntentCategory.ESCALATION, IntentCategory.HUMAN_HANDOFF):
            return UrgencyLevel.HIGH
        if intent == IntentCategory.COMPLAINT:
            return UrgencyLevel.MEDIUM
        return UrgencyLevel.LOW

    def _cache_key(self, message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        payload = {"message": self._clean_text(message)[:200]}
        if history:
            payload["history"] = [
                {
                    "role": self._clean_text(item.get("role", ""))[:20],
                    "content": self._clean_text(item.get("content", ""))[:160],
                }
                for item in history[-3:]
            ]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _unique(values: List[str]) -> List[str]:
        return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))

    @staticmethod
    def _best_pattern_match(
        message: str,
        patterns: Dict[IntentCategory, List[str]],
    ) -> tuple[IntentCategory, float]:
        best_cat, best_score = IntentCategory.OTHER, 0.0
        for cat, kws in patterns.items():
            hits = sum(1 for kw in kws if kw in message)
            if not hits:
                continue
            # 单个明确业务关键词就给可用置信度；多个关键词命中时提高置信度。
            score = min(1.0, 0.5 + 0.25 * (hits - 1))
            if score > best_score:
                best_score, best_cat = score, cat
        return best_cat, best_score

    @staticmethod
    def _intent_group(intent: IntentCategory) -> str:
        return _INTENT_GROUPS.get(intent, intent).value

    @staticmethod
    def _clean_text(value: Any) -> str:
        """移除 Unicode 代理字符，避免 HTTP 客户端编码 prompt 时崩溃。"""
        if value is None:
            return ""
        if not isinstance(value, str):
            value = str(value)
        return value.encode("utf-8", errors="ignore").decode("utf-8")

    @property
    def cache_stats(self) -> Dict[str, Any]:
        total = self.cache_hits + self.cache_misses
        return {
            "size": len(self._cache),
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "hit_rate": self.cache_hits / total if total else 0.0,
        }
