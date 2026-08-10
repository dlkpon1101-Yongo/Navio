// Navio 前端 — 仅连接 Python 后端（FastAPI）
const DEFAULT_BACKEND = {
  id: 'python',
  label: 'Python',
  baseUrl: import.meta.env.VITE_PYTHON_API_URL || '/api/python',
  port: '8000'
}

const STORAGE_KEY = 'navio.frontend.settings'

export function createInitialSettings() {
  const saved = readSettings()
  return {
    userId: saved.userId || 'u1001',
    conversationId: saved.conversationId || '',
    // 兼容旧版存储结构（旧版曾包含 backend / endpoints.java 字段）
    apiUrl: saved.apiUrl || saved.endpoints?.python || DEFAULT_BACKEND.baseUrl
  }
}

export function saveSettings(settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

export function backendMeta(settings) {
  return {
    ...DEFAULT_BACKEND,
    baseUrl: normalizeBaseUrl(settings.apiUrl || DEFAULT_BACKEND.baseUrl)
  }
}

export async function requestHealth(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/health')
}

export async function requestMonitor(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/monitor')
}

export async function requestKnowledgeStats(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/knowledge/stats')
}

export async function requestSearch(settings, query, topK = 5) {
  const params = new URLSearchParams({ query, topK: String(topK) })
  return requestJson(backendMeta(settings).baseUrl, `/search?${params}`, { method: 'POST' })
}

export async function requestChat(settings, message) {
  const meta = backendMeta(settings)
  const payload = {
    message,
    user_id: settings.userId || 'anonymous',
    conv_id: settings.conversationId || undefined
  }
  const raw = await requestJson(meta.baseUrl, '/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return normalizeChatResponse(raw)
}

export async function addKnowledge(settings, documents) {
  return requestJson(backendMeta(settings).baseUrl, '/knowledge/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ documents })
  })
}

export async function uploadKnowledge(settings, file) {
  const form = new FormData()
  form.append('file', file)
  return requestJson(backendMeta(settings).baseUrl, '/knowledge/upload', {
    method: 'POST',
    body: form
  })
}

function normalizeChatResponse(raw) {
  return {
    conversationId: raw.conv_id || raw.conversation_id || '',
    response: raw.response || '',
    intent: raw.intent || 'other',
    agentType: raw.agent_type || '',
    escalated: Boolean(raw.escalated),
    latencyMs: Number(raw.latency_ms ?? 0),
    knowledgeUsed: Boolean(raw.knowledge_used),
    raw
  }
}

async function requestJson(baseUrl, path, options = {}) {
  const url = `${normalizeBaseUrl(baseUrl)}${path}`
  const response = await fetch(url, options)
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!response.ok) {
    const detail = typeof data === 'string' ? data : JSON.stringify(data)
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
  return data
}

function normalizeBaseUrl(value) {
  return String(value || '').replace(/\/+$/, '')
}

function readSettings() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}
