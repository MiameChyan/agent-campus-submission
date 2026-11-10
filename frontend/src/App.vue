<script setup>
import { ref, computed } from 'vue'

const question = ref('报销期限多久？')
const useMock = ref(false)
const kb = ref('')
const fail = ref('')
const history = ref([])          // 多轮对话：每轮的问题、答案、引用
const steps = ref([])            // 当前这一轮的实时 trace
const result = ref(null)
const running = ref(false)
const error = ref('')

const STATUS_TEXT = {
  answered: '已回答',
  conflict_needs_confirmation: '资料冲突，需确认',
  out_of_scope: '资料范围外',
  need_clarification: '需要补充信息',
  tool_error: '工具故障',
  incomplete: '未完成（达到上限）',
  model_error: '模型调用失败',
}
const statusText = computed(() => (result.value ? STATUS_TEXT[result.value.status] || result.value.status : ''))

async function ask() {
  if (!question.value.trim() || running.value) return
  running.value = true
  steps.value = []
  result.value = null
  error.value = ''
  const body = {
    question: question.value,
    history: history.value,
    mock: useMock.value,
    kb: kb.value || null,
    fail: fail.value || null,
  }
  try {
    const resp = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`)
    // 读取 SSE：每个事件形如 "event: step\ndata: {...}\n\n"
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const event = /^event: (.*)$/m.exec(block)?.[1]
        const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] || '{}')
        if (event === 'step') steps.value.push(data)
        else if (event === 'final') result.value = data
        else if (event === 'error') error.value = data.message
      }
    }
    if (result.value && ['answered', 'conflict_needs_confirmation', 'need_clarification'].includes(result.value.status)) {
      history.value.push({
        question: question.value,
        answer: result.value.answer || result.value.clarifying_question || '',
        citations: result.value.citations.map((c) => ({ doc_id: c.doc_id, section_id: c.section_id })),
      })
    }
  } catch (e) {
    error.value = String(e)
  } finally {
    running.value = false
  }
}

function clearHistory() {
  history.value = []
  steps.value = []
  result.value = null
}
</script>

<template>
  <main>
    <header>
      <h1>企业知识问答 Agent</h1>
      <span class="hint">DeepSeek · 层次型知识库 · ReAct</span>
    </header>

    <section class="panel">
      <form @submit.prevent="ask">
        <input v-model="question" placeholder="输入问题，如：报销期限多久？" :disabled="running" />
        <button :disabled="running">{{ running ? '运行中…' : '提问' }}</button>
      </form>
      <div class="options">
        <label><input type="checkbox" v-model="useMock" /> 离线 Mock（只验证流程）</label>
        <label>知识库
          <select v-model="kb">
            <option value="">默认 data/kb</option>
            <option value="no_conflict">变体 no_conflict（去掉 D02）</option>
          </select>
        </label>
        <label>故障注入 <input v-model="fail" placeholder="如 search:always" class="short" /></label>
        <button type="button" class="link" @click="clearHistory">清空对话（{{ history.length }} 轮）</button>
      </div>
      <ol v-if="history.length" class="history">
        <li v-for="(h, i) in history" :key="i"><b>问：</b>{{ h.question }}</li>
      </ol>
    </section>

    <section class="panel" v-if="steps.length || running">
      <h2>执行轨迹</h2>
      <table>
        <thead><tr><th>#</th><th>轮</th><th>动作</th><th>参数</th><th>返回摘要</th><th>决策依据</th></tr></thead>
        <tbody>
          <tr v-for="s in steps" :key="s.step" :class="{ bad: !s.ok }">
            <td>{{ s.step }}</td>
            <td>{{ s.turn }}</td>
            <td><code>{{ s.action }}</code></td>
            <td><code class="args">{{ JSON.stringify(s.args) }}</code></td>
            <td>{{ s.observation }}</td>
            <td>{{ s.reason }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="running" class="hint">模型思考中…</p>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="panel" v-if="result">
      <h2>结果 <span class="badge" :class="result.status">{{ statusText }}</span></h2>
      <p v-if="result.answer" class="answer">{{ result.answer }}</p>
      <p v-if="result.clarifying_question" class="answer">追问：{{ result.clarifying_question }}</p>

      <h3 v-if="result.citations.length">引用</h3>
      <ul>
        <li v-for="(c, i) in result.citations" :key="i">
          <b>{{ c.doc_id }}#{{ c.section_id }}</b>《{{ c.title }}》{{ c.section_title }}
          <span class="hint">（{{ c.version_date }}，{{ c.doc_status }}）</span>
          <blockquote>{{ c.quote }}</blockquote>
        </li>
      </ul>

      <h3 v-if="result.conflicts.length">冲突</h3>
      <ul><li v-for="(c, i) in result.conflicts" :key="i">{{ c.description }}（{{ c.doc_ids.join('、') }}）</li></ul>

      <h3 v-if="result.gaps.length">资料缺口</h3>
      <ul><li v-for="(g, i) in result.gaps" :key="i">{{ g }}</li></ul>

      <p class="hint">
        模式 {{ result.mode }} · 模型 {{ result.model }} · 知识库 {{ result.kb }} ·
        模型 {{ result.stats.llm_turns }} 轮 / 工具 {{ result.stats.tool_calls }} 次 · {{ result.stats.elapsed_ms }} ms
      </p>
    </section>
  </main>
</template>

<style>
body { margin: 0; font-family: system-ui, -apple-system, 'Microsoft YaHei', sans-serif; background: #f6f7f9; color: #1f2328; }
main { max-width: 1100px; margin: 0 auto; padding: 16px; }
header { display: flex; align-items: baseline; gap: 12px; }
h1 { font-size: 22px; margin: 8px 0; }
h2 { font-size: 17px; margin: 0 0 10px; }
h3 { font-size: 15px; margin: 14px 0 6px; }
.panel { background: #fff; border: 1px solid #d8dee4; border-radius: 8px; padding: 14px; margin: 12px 0; overflow-x: auto; }
form { display: flex; gap: 8px; }
form input { flex: 1; padding: 8px 10px; font-size: 15px; border: 1px solid #c4cbd3; border-radius: 6px; }
button { padding: 8px 16px; border: 0; border-radius: 6px; background: #0969da; color: #fff; cursor: pointer; }
button:disabled { opacity: .6; cursor: default; }
button.link { background: none; color: #0969da; padding: 0; }
.options { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 10px; font-size: 14px; align-items: center; }
.short { width: 160px; padding: 3px 6px; }
.history { font-size: 13px; color: #57606a; margin: 8px 0 0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #eaeef2; padding: 6px; text-align: left; vertical-align: top; }
tr.bad td { background: #fff5f5; }
code.args { white-space: pre-wrap; word-break: break-all; }
.answer { white-space: pre-wrap; line-height: 1.6; }
blockquote { margin: 4px 0 8px; padding: 4px 10px; border-left: 3px solid #0969da; background: #f6f8fa; }
.hint { color: #6e7781; font-size: 13px; }
.error { color: #cf222e; }
.badge { font-size: 13px; padding: 2px 8px; border-radius: 10px; background: #eaeef2; margin-left: 6px; }
.badge.answered { background: #dafbe1; color: #116329; }
.badge.conflict_needs_confirmation, .badge.need_clarification { background: #fff8c5; color: #7d4e00; }
.badge.tool_error, .badge.model_error, .badge.incomplete { background: #ffebe9; color: #a40e26; }
</style>
