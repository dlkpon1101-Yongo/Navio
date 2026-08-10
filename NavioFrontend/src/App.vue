<template>
  <main class="app-shell">
    <aside class="sidebar">
      <section class="brand">
        <div class="brand-mark">NV</div>
        <div>
          <h1>Navio Console</h1>
          <p>Navio 后端调试控制台</p>
        </div>
      </section>

      <a class="profile-card" href="https://github.com/dlkpon1101-Yongo" target="_blank" rel="noreferrer">
        <span>我的主页</span>
        <strong>dlkpon1101-Yongo</strong>
        <em>前往我的 GitHub 主页 &gt;&gt;</em>
      </a>

      <section class="panel">
        <div class="panel-heading">
          <h2>后端</h2>
          <span class="pill">{{ currentBackend.label }}</span>
        </div>

        <label>
          <span>API 地址</span>
          <input v-model="settings.apiUrl" @change="persist" placeholder="/api/python" />
        </label>
        <label>
          <span>用户 ID</span>
          <input v-model="settings.userId" @change="persist" placeholder="u1001" />
        </label>
        <label>
          <span>会话 ID</span>
          <input v-model="settings.conversationId" @change="persist" placeholder="自动生成" />
        </label>

        <div class="actions">
          <button @click="checkHealth">健康检查</button>
          <button @click="loadStats">刷新状态</button>
        </div>
      </section>

      <section class="panel status-panel">
        <div class="panel-heading">
          <h2>状态</h2>
          <span :class="['status-dot', healthOk ? 'online' : 'offline']"></span>
        </div>
        <dl>
          <div>
            <dt>当前后端</dt>
            <dd>{{ currentBackend.label }}</dd>
          </div>
          <div>
            <dt>健康状态</dt>
            <dd :class="healthOk ? 'ok' : 'muted'">{{ healthLabel }}</dd>
          </div>
          <div>
            <dt>知识片段</dt>
            <dd>{{ knowledgeCount }}</dd>
          </div>
        </dl>
        <pre v-if="statusText">{{ statusText }}</pre>
      </section>
    </aside>

    <section class="workspace">
      <header class="workspace-header">
        <div>
          <span class="eyebrow">Navio Workspace</span>
          <h2>对话调试</h2>
          <p>{{ currentBackend.baseUrl }}</p>
        </div>
        <div class="header-actions">
          <a class="profile-link" href="https://github.com/dlkpon1101-Yongo" target="_blank" rel="noreferrer">GitHub 主页</a>
          <a :href="docsUrl" target="_blank" rel="noreferrer">API 文档</a>
        </div>
      </header>

      <section class="chat-panel">
        <div class="messages" ref="messageList">
          <article v-for="item in messages" :key="item.id" :class="['message', item.role]">
            <div class="message-meta">
              <span>{{ item.role === 'user' ? '用户' : currentBackend.label }}</span>
              <small v-if="item.meta">{{ item.meta }}</small>
            </div>
            <p>{{ item.content }}</p>
          </article>
          <div v-if="messages.length === 0" class="empty-state">
            <h3>开始一次客服对话</h3>
            <p>连接 Navio Python 后端，支持意图识别、多 Agent 路由与知识库检索。</p>
          </div>
        </div>

        <form class="composer" @submit.prevent="sendMessage">
          <textarea v-model="draft" rows="3" placeholder="输入问题，例如：这款理财产品年化收益多少？"></textarea>
          <button :disabled="busy || !draft.trim()">{{ busy ? '发送中' : '发送' }}</button>
        </form>
      </section>

      <section class="tools-grid">
        <article class="tool-panel">
          <div class="panel-heading">
            <h2>知识库检索</h2>
            <span class="pill soft">RAG</span>
          </div>
          <div class="inline-form">
            <input v-model="searchQuery" placeholder="退款多久能到账" />
            <button @click="searchKnowledge" :disabled="busy || !searchQuery.trim()">检索</button>
          </div>
          <div class="result-list">
            <article v-for="item in searchResults" :key="item.id || item.title" class="result-item">
              <strong>{{ item.title || '未命名结果' }}</strong>
              <span>score {{ item.score ?? '-' }}</span>
              <p>{{ item.content }}</p>
            </article>
          </div>
        </article>

        <article class="tool-panel">
          <div class="panel-heading">
            <h2>导入知识</h2>
            <span class="pill soft">Docs</span>
          </div>
          <label>
            <span>标题</span>
            <input v-model="docTitle" placeholder="退款补充政策" />
          </label>
          <label>
            <span>内容</span>
            <textarea v-model="docContent" rows="5" placeholder="输入知识库内容"></textarea>
          </label>
          <div class="actions">
            <button @click="submitKnowledge" :disabled="busy || !docTitle.trim() || !docContent.trim()">添加文档</button>
            <label class="file-button">
              上传文件
              <input type="file" accept=".txt,.md,.json" @change="handleUpload" />
            </label>
          </div>
        </article>
      </section>
    </section>
  </main>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import {
  addKnowledge,
  backendMeta,
  createInitialSettings,
  requestChat,
  requestHealth,
  requestKnowledgeStats,
  requestMonitor,
  requestSearch,
  saveSettings,
  uploadKnowledge
} from './lib/backends'

const settings = reactive(createInitialSettings())
const messages = ref([])
const draft = ref('')
const busy = ref(false)
const healthOk = ref(false)
const healthLabel = ref('未检查')
const statusText = ref('')
const knowledgeCount = ref('-')
const searchQuery = ref('这款理财的年化收益多少？')
const searchResults = ref([])
const docTitle = ref('理财产品说明')
const docContent = ref('该产品起购金额1万元，业绩比较基准年化3.2%～3.8%，风险等级R2，期限90天。锁定期后每周三开放赎回，到期自动赎回。')
const messageList = ref(null)

const currentBackend = computed(() => backendMeta(settings))
const docsUrl = computed(() => `${currentBackend.value.baseUrl}/docs`)

watch(
  () => settings.conversationId,
  () => persist()
)

onMounted(() => {
  checkHealth()
  loadStats()
})

function persist() {
  saveSettings(settings)
}

async function sendMessage() {
  const content = draft.value.trim()
  if (!content) return
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content })
  draft.value = ''
  busy.value = true
  try {
    const response = await requestChat(settings, content)
    if (response.conversationId && !settings.conversationId) {
      settings.conversationId = response.conversationId
      persist()
    }
    const meta = [
      response.intent,
      response.agentType,
      response.knowledgeUsed ? 'RAG' : '',
      response.escalated ? '转人工' : ''
    ].filter(Boolean).join(' · ')
    messages.value.push({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: response.response,
      meta
    })
  } catch (error) {
    messages.value.push({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: error.message,
      meta: '请求失败'
    })
  } finally {
    busy.value = false
    await nextTick()
    messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' })
  }
}

async function checkHealth() {
  try {
    const data = await requestHealth(settings)
    healthOk.value = data.status === 'ok'
    healthLabel.value = data.status || 'ok'
    statusText.value = JSON.stringify(data, null, 2)
  } catch (error) {
    healthOk.value = false
    healthLabel.value = '不可用'
    statusText.value = error.message
  }
}

async function loadStats() {
  try {
    const [stats, monitor] = await Promise.allSettled([
      requestKnowledgeStats(settings),
      requestMonitor(settings)
    ])
    if (stats.status === 'fulfilled') {
      knowledgeCount.value = stats.value.total_chunks ?? stats.value.totalChunks ?? '-'
    }
    if (monitor.status === 'fulfilled') {
      statusText.value = JSON.stringify(monitor.value, null, 2)
    }
  } catch (error) {
    statusText.value = error.message
  }
}

async function searchKnowledge() {
  busy.value = true
  try {
    const data = await requestSearch(settings, searchQuery.value, 5)
    searchResults.value = data.results || []
  } catch (error) {
    statusText.value = error.message
  } finally {
    busy.value = false
  }
}

async function submitKnowledge() {
  busy.value = true
  try {
    const data = await addKnowledge(settings, [
      { title: docTitle.value.trim(), content: docContent.value.trim() }
    ])
    statusText.value = JSON.stringify(data, null, 2)
    await loadStats()
  } catch (error) {
    statusText.value = error.message
  } finally {
    busy.value = false
  }
}

async function handleUpload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  busy.value = true
  try {
    const data = await uploadKnowledge(settings, file)
    statusText.value = JSON.stringify(data, null, 2)
    await loadStats()
  } catch (error) {
    statusText.value = error.message
  } finally {
    busy.value = false
  }
}
</script>
