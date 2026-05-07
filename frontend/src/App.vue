<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

const topic = ref('')
const numSlides = ref(10)
const fileInput = ref(null)
const selectedFiles = ref([])
const loading = ref(false)
const errorMsg = ref('')
const statusMsg = ref('')
const downloadUrl = ref('')
const downloadName = ref('')
const lastDropAt = ref(0)

const canSubmit = computed(() => topic.value.trim().length > 0 && !loading.value)

function revokeDownload() {
  if (downloadUrl.value) {
    URL.revokeObjectURL(downloadUrl.value)
    downloadUrl.value = ''
    downloadName.value = ''
  }
}

function parseFilename(header) {
  if (!header) return 'presentation.pptx'
  const star = /filename\*=UTF-8''([^;\n]+)/i.exec(header)
  if (star) {
    try {
      return decodeURIComponent(star[1].trim())
    } catch {
      return star[1].trim()
    }
  }
  const quoted = /filename="([^"]+)"/i.exec(header)
  if (quoted) return quoted[1].trim()
  const plain = /filename=([^;\n]+)/i.exec(header)
  if (plain) return plain[1].trim().replace(/^"|"$/g, '')
  return 'presentation.pptx'
}

function setFiles(list) {
  selectedFiles.value = list
  statusMsg.value = list.length ? `已选择 ${list.length} 个文件` : ''
}

function onFileChange(e) {
  setFiles(Array.from(e.target.files || []))
}

function onDragOver(e) {
  e.preventDefault()
  e.dataTransfer.dropEffect = 'copy'
}

function onDrop(e) {
  e.preventDefault()
  lastDropAt.value = Date.now()
  const dt = e.dataTransfer
  if (!dt?.files?.length) return
  setFiles(Array.from(dt.files))
  if (fileInput.value) fileInput.value.value = ''
}

function openPicker() {
  if (Date.now() - lastDropAt.value < 500) return
  fileInput.value?.click()
}

function removeAt(index) {
  const next = selectedFiles.value.filter((_, i) => i !== index)
  setFiles(next)
  if (fileInput.value) fileInput.value.value = ''
}

function formatDetail(detail) {
  if (detail == null) return '请求失败'
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((x) => (typeof x === 'object' && x?.msg ? x.msg : JSON.stringify(x)))
      .join('；')
  }
  return JSON.stringify(detail)
}

async function generate() {
  errorMsg.value = ''
  statusMsg.value = ''
  revokeDownload()

  if (!topic.value.trim()) {
    errorMsg.value = '请填写演示主题'
    return
  }

  loading.value = true
  try {
    const fd = new FormData()
    fd.append('topic', topic.value.trim())
    fd.append('num_slides', String(Number(numSlides.value) || 10))
    for (const f of selectedFiles.value) {
      fd.append('files', f)
    }

    const res = await fetch('/api/generate', {
      method: 'POST',
      body: fd,
    })

    if (!res.ok) {
      let detail = '生成失败'
      try {
        const j = await res.json()
        detail = formatDetail(j.detail)
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const name = parseFilename(res.headers.get('Content-Disposition'))
    downloadUrl.value = url
    downloadName.value = name

    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.rel = 'noopener'
    a.click()

    statusMsg.value = '已开始下载，若被浏览器拦截请使用下方链接手动保存。'
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onBeforeUnmount(() => {
  revokeDownload()
})
</script>

<template>
  <div class="page">
    <div class="bg-grid" aria-hidden="true" />

    <header class="top">
      <div class="top-inner">
        <div class="brand">
          <span class="brand-glyph" aria-hidden="true" />
          <div class="brand-copy">
            <p class="kicker">演示文稿工作台</p>
            <h1 class="brand-title">PPT Genius</h1>
            <p class="brand-sub">
              用主题定调、用资料压实内容：先生成叙事大纲，再把检索到的素材改写进正文段落与要点，最后导出标准
              pptx。
            </p>
          </div>
        </div>
      </div>
    </header>

    <div class="layout">
      <main class="primary">
        <section class="block" aria-labelledby="sec-form">
          <div class="block-head">
            <h2 id="sec-form" class="block-title">新建生成任务</h2>
            <p class="block-desc">
              主题会驱动整体叙事结构；上传的文件会优先参与检索，并被写进各页正文。
            </p>
          </div>

          <div class="field">
            <label class="label" for="topic">演示主题</label>
            <input
              id="topic"
              v-model="topic"
              class="input"
              type="text"
              name="topic"
              autocomplete="off"
              placeholder="例如：区县政务数据共享平台建设中期汇报"
            />
          </div>

          <div class="field field-row">
            <div class="field-grow">
              <label class="label" for="slides">幻灯片页数</label>
              <div class="num-wrap">
                <input
                  id="slides"
                  v-model.number="numSlides"
                  class="input input-num"
                  type="number"
                  min="1"
                  max="40"
                  name="num_slides"
                />
                <span class="hint">建议 8–16 页；上限 40</span>
              </div>
            </div>
          </div>

          <div class="field">
            <span class="label" id="upload-label">参考资料（可选）</span>
            <p class="field-help">支持多文件；文本越长，可供改写的内容越多。</p>
            <div
              class="drop"
              :class="{ 'drop-active': selectedFiles.length > 0 }"
              role="button"
              tabindex="0"
              aria-labelledby="upload-label"
              @click="openPicker"
              @keydown.enter.prevent="openPicker"
              @keydown.space.prevent="openPicker"
              @dragover="onDragOver"
              @drop="onDrop"
            >
              <span class="drop-label">放置或选择文件</span>
              <span class="drop-hint">TXT、Markdown、PDF、Word（docx）、CSV、JSON</span>
            </div>
            <input
              ref="fileInput"
              class="sr-only"
              type="file"
              multiple
              accept=".txt,.md,.markdown,.pdf,.docx,.csv,.json"
              @change="onFileChange"
            />

            <ul v-if="selectedFiles.length" class="file-list">
              <li v-for="(f, i) in selectedFiles" :key="`${f.name}-${i}`" class="file-row">
                <span class="file-dot" aria-hidden="true" />
                <span class="file-name" :title="f.name">{{ f.name }}</span>
                <button type="button" class="file-remove" @click.stop="removeAt(i)">移除</button>
              </li>
            </ul>
          </div>

          <div class="actions">
            <button type="button" class="btn" :disabled="!canSubmit" @click="generate">
              <span v-if="loading" class="btn-spinner" aria-hidden="true" />
              <span>{{ loading ? '正在生成演示文稿' : '生成并下载 pptx' }}</span>
            </button>
            <p v-if="loading" class="actions-note">首次调用大模型可能稍慢，请保持页面打开。</p>
          </div>

          <div v-if="statusMsg || errorMsg || downloadUrl" class="feedback">
            <p v-if="statusMsg" class="feedback ok">{{ statusMsg }}</p>
            <p v-if="errorMsg" class="feedback err" role="alert">{{ errorMsg }}</p>
            <div v-if="downloadUrl" class="fallback">
              <span class="fallback-label">备用链接</span>
              <a class="fallback-link" :href="downloadUrl" :download="downloadName">{{ downloadName }}</a>
            </div>
          </div>
        </section>

        <!-- <section class="block flow-block" aria-labelledby="sec-flow">
          <h2 id="sec-flow" class="block-title flow-title">后台大致在做什么</h2>
          <ol class="flow">
            <li class="flow-step">
              <span class="flow-idx">1</span>
              <div class="flow-body">
                <strong class="flow-name">结构化大纲</strong>
                <span class="flow-text">按页规划标题与叙事锚点，保证起承转合可读。</span>
              </div>
            </li>
            <li class="flow-step">
              <span class="flow-idx">2</span>
              <div class="flow-body">
                <strong class="flow-name">素材检索与改写</strong>
                <span class="flow-text">优先匹配你上传的段落，再补充内置知识库；模型把材料揉进段落与条目。</span>
              </div>
            </li>
            <li class="flow-step">
              <span class="flow-idx">3</span>
              <div class="flow-body">
                <strong class="flow-name">排版导出</strong>
                <span class="flow-text">生成含标题、正文段与要点列表的幻灯片，备注区保留简要溯源线索。</span>
              </div>
            </li>
          </ol>
        </section> -->
      </main>

      <aside class="rail" aria-label="说明与提示">
        <div class="rail-section">
          <h3 class="rail-heading">怎么写出更像「成品」的稿</h3>
          <ul class="rail-list">
            <li>主题尽量包含受众与场景（如「向校方汇报」「给对方案评审」）。</li>
            <li>上传资料里若有数据、流程或专有名词，更容易被写进正文。</li>
            <li>页数偏少时信息更集中；页数多时会拆细叙事，但仍受单次生成篇幅限制。</li>
          </ul>
        </div>

        <!-- <div class="rail-section">
          <h3 class="rail-heading">环境与密钥</h3>
          <p class="rail-p">
            后端读取仓库根目录的 <code class="code">.env</code>（如 <code class="code">OPENAI_API_KEY</code>、
            <code class="code">OPENAI_BASE_URL</code>、<code class="code">PPTGENIUS_MODEL</code>）。未配置时将使用离线占位大纲，正文深度会明显下降。
          </p>
        </div>

        <details class="rail-details">
          <summary class="rail-summary">本地开发如何联调</summary>
          <div class="rail-details-body">
            <p class="rail-p">
              终端一：<code class="code">python -m ppt_generator.server</code>（默认端口 8000）。终端二：在
              <code class="code">frontend</code> 目录执行 <code class="code">npm run dev</code>。
            </p>
            <p class="rail-p muted-soft">
              Vite 已将 <code class="code">/api</code> 代理到后端。上线时请改为同源反向代理，并在服务端配置
              <code class="code">PPTGENIUS_CORS_ORIGINS</code>。
            </p>
          </div>
        </details> -->
      </aside>
    </div>

    <footer class="foot">
      <div class="foot-inner">
        <p class="foot-line">
          <span class="foot-brand">PPT Genius</span>
          <span class="foot-sep" aria-hidden="true" />
          <span>LLM 结构化生成与稀疏检索增强</span>
        </p>
      </div>
    </footer>
  </div>
</template>

<style>
:root {
  --bg: #f0ebe2;
  --bg-elev: #faf7f1;
  --fg: #161412;
  --muted: #5f584f;
  --muted-soft: #7a7268;
  --line: #dcd4c8;
  --line-strong: #c9bfb2;
  --accent: #1a6b58;
  --accent-hover: #145546;
  --rust: #ae4f2b;
  --amber: #b45309;
  --danger: #8b3a1f;
  --shadow-field: 0 1px 2px rgba(22, 20, 18, 0.05);
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, Segoe UI, sans-serif;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
}

.page {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
}

.bg-grid {
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(ellipse 900px 520px at 12% -8%, rgba(174, 79, 43, 0.07), transparent 55%),
    radial-gradient(ellipse 700px 480px at 92% 6%, rgba(26, 107, 88, 0.09), transparent 52%),
    radial-gradient(ellipse 600px 400px at 50% 108%, rgba(180, 83, 9, 0.06), transparent 45%),
    linear-gradient(180deg, #ebe4d8 0%, var(--bg) 38%, #ebe6dc 100%);
  opacity: 1;
}

.bg-grid::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(92, 84, 74, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(92, 84, 74, 0.045) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 75% 65% at 50% 35%, black 15%, transparent 70%);
}

.top {
  position: relative;
  z-index: 1;
  border-bottom: 1px solid color-mix(in srgb, var(--line) 88%, var(--fg));
}

.top-inner {
  max-width: 68rem;
  margin: 0 auto;
  padding: 2rem 1.5rem 1.75rem;
}

.brand {
  display: flex;
  gap: 1.25rem;
  align-items: flex-start;
  max-width: 46rem;
}

.brand-glyph {
  flex-shrink: 0;
  width: 3px;
  margin-top: 0.4rem;
  min-height: 4.25rem;
  border-radius: 999px;
  background: linear-gradient(185deg, var(--accent) 0%, var(--rust) 48%, var(--amber) 100%);
}

.kicker {
  margin: 0 0 0.35rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--muted-soft);
}

.brand-title {
  margin: 0;
  font-family: 'Fraunces', Georgia, serif;
  font-size: clamp(1.85rem, 4vw, 2.35rem);
  font-weight: 700;
  font-variation-settings: 'opsz' 72;
  letter-spacing: -0.03em;
  line-height: 1.12;
  color: var(--fg);
}

.brand-sub {
  margin: 0.85rem 0 0;
  font-size: 1rem;
  line-height: 1.65;
  color: var(--muted);
  max-width: 38rem;
}

.layout {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(15rem, 17.5rem);
  gap: 2.5rem 3rem;
  align-items: start;
  max-width: 68rem;
  margin: 0 auto;
  padding: 2.25rem 1.5rem 3rem;
}

@media (max-width: 960px) {
  .layout {
    grid-template-columns: 1fr;
    gap: 2rem;
  }

  .rail {
    padding-top: 0;
    border-left: none;
    border-top: 1px solid var(--line);
    padding-left: 0;
    padding-top: 2rem;
  }
}

.primary {
  min-width: 0;
}

.block {
  padding-bottom: 2.25rem;
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--line);
}

.block:last-of-type {
  border-bottom: none;
  margin-bottom: 0;
}

.block-head {
  margin-bottom: 1.35rem;
}

.block-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg);
}

.block-desc {
  margin: 0.45rem 0 0;
  font-size: 0.9rem;
  line-height: 1.6;
  color: var(--muted);
  max-width: 40rem;
}

.field {
  margin-top: 1.15rem;
}

.field-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.field-grow {
  flex: 1;
  min-width: 12rem;
}

.label {
  display: block;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted-soft);
  margin-bottom: 0.4rem;
}

.field-help {
  margin: -0.15rem 0 0.5rem;
  font-size: 0.82rem;
  color: var(--muted-soft);
  line-height: 1.45;
}

.input {
  width: 100%;
  padding: 0.72rem 0.9rem;
  border-radius: 12px;
  border: 1px solid var(--line-strong);
  background: var(--bg-elev);
  font: inherit;
  color: var(--fg);
  outline: none;
  box-shadow: var(--shadow-field);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

.input:hover {
  border-color: color-mix(in srgb, var(--line-strong) 70%, var(--muted));
}

.input:focus-visible {
  border-color: color-mix(in srgb, var(--amber) 55%, var(--accent));
  box-shadow:
    var(--shadow-field),
    0 0 0 3px color-mix(in srgb, var(--amber) 22%, transparent);
}

.input-num {
  max-width: 7rem;
}

.num-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem 1rem;
}

.hint {
  font-size: 0.82rem;
  color: var(--muted-soft);
}

.drop {
  margin-top: 0.35rem;
  padding: 1.35rem 1.25rem;
  border-radius: 16px;
  border: 2px dashed color-mix(in srgb, var(--line-strong) 82%, var(--accent) 18%);
  background: color-mix(in srgb, var(--bg-elev) 94%, transparent);
  cursor: pointer;
  outline: none;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    transform 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.drop:hover,
.drop:focus-visible {
  border-color: color-mix(in srgb, var(--accent) 42%, var(--line-strong));
  background: var(--bg-elev);
}

.drop:active {
  transform: scale(0.995);
}

.drop-active {
  border-style: solid;
  border-color: color-mix(in srgb, var(--accent) 35%, var(--line-strong));
  background: color-mix(in srgb, var(--accent) 6%, var(--bg-elev));
}

.drop-label {
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--fg);
}

.drop-hint {
  font-size: 0.82rem;
  color: var(--muted);
}

.file-list {
  list-style: none;
  margin: 0.85rem 0 0;
  padding: 0;
}

.file-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.55rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid color-mix(in srgb, var(--line) 78%, transparent);
  font-size: 0.88rem;
}

.file-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.65;
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-remove {
  border: none;
  background: none;
  padding: 0.2rem 0.35rem;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--rust);
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.file-remove:hover {
  background: color-mix(in srgb, var(--rust) 12%, transparent);
}

.actions {
  margin-top: 1.65rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.65rem;
}

.btn {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  border: none;
  border-radius: 999px;
  padding: 0.78rem 1.6rem;
  font: inherit;
  font-weight: 700;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
  color: #fff;
  background: linear-gradient(165deg, #1f7a66 0%, var(--accent) 45%, #134d40 100%);
  cursor: pointer;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.12) inset,
    0 8px 22px rgba(26, 107, 88, 0.28);
  transition:
    transform 0.12s ease,
    box-shadow 0.18s ease,
    filter 0.18s ease;
}

.btn:hover:not(:disabled) {
  filter: brightness(1.05);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.14) inset,
    0 10px 28px rgba(26, 107, 88, 0.34);
}

.btn:active:not(:disabled) {
  transform: translateY(1px);
}

.btn:disabled {
  opacity: 0.48;
  cursor: not-allowed;
  box-shadow: none;
}

.btn-spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.65s linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .btn-spinner {
    animation: none;
    border-top-color: rgba(255, 255, 255, 0.55);
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.actions-note {
  margin: 0;
  font-size: 0.82rem;
  color: var(--muted-soft);
}

.feedback {
  margin-top: 1.25rem;
  padding-top: 1.15rem;
  border-top: 1px dashed var(--line);
}

.feedback.ok {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--accent-hover);
}

.feedback.err {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--danger);
}

.feedback.ok + .feedback.err {
  margin-top: 0.65rem;
}

.fallback {
  margin-top: 0.75rem;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.65rem;
  font-size: 0.86rem;
}

.fallback-label {
  font-weight: 700;
  color: var(--muted-soft);
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.fallback-link {
  color: var(--accent-hover);
  font-weight: 700;
  text-underline-offset: 3px;
}

.flow-block {
  padding-bottom: 0;
  margin-bottom: 0;
  border-bottom: none;
}

.flow-title {
  margin-bottom: 1rem;
}

.flow {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.flow-step {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.85rem 1rem;
  padding: 0.85rem 0;
  border-top: 1px solid var(--line);
}

.flow-step:last-child {
  padding-bottom: 0;
}

.flow-idx {
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.82rem;
  font-weight: 800;
  color: var(--accent-hover);
  background: color-mix(in srgb, var(--accent) 11%, var(--bg-elev));
  border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--line));
}

.flow-body {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.flow-name {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--fg);
}

.flow-text {
  font-size: 0.86rem;
  line-height: 1.55;
  color: var(--muted);
}

.rail {
  position: relative;
  padding-left: 2rem;
  border-left: 1px solid color-mix(in srgb, var(--accent) 18%, var(--line));
}

.rail-section + .rail-section {
  margin-top: 1.75rem;
}

.rail-heading {
  margin: 0 0 0.65rem;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted-soft);
}

.rail-list {
  margin: 0;
  padding: 0 0 0 1rem;
  font-size: 0.86rem;
  line-height: 1.65;
  color: var(--muted);
}

.rail-list li {
  margin-bottom: 0.45rem;
}

.rail-list li::marker {
  color: var(--rust);
}

.rail-p {
  margin: 0;
  font-size: 0.86rem;
  line-height: 1.65;
  color: var(--muted);
}

.muted-soft {
  color: var(--muted-soft);
}

.code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78em;
  padding: 0.12rem 0.38rem;
  border-radius: 6px;
  background: color-mix(in srgb, var(--line) 42%, var(--bg-elev));
  border: 1px solid color-mix(in srgb, var(--line-strong) 65%, transparent);
}

.rail-details {
  margin-top: 1.75rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--line);
}

.rail-summary {
  cursor: pointer;
  font-size: 0.88rem;
  font-weight: 700;
  color: var(--fg);
  list-style: none;
}

.rail-summary::-webkit-details-marker {
  display: none;
}

.rail-summary::after {
  content: '+';
  float: right;
  font-weight: 800;
  color: var(--muted-soft);
}

details[open] .rail-summary::after {
  content: '−';
}

.rail-details-body {
  margin-top: 0.75rem;
}

.rail-details-body .rail-p + .rail-p {
  margin-top: 0.55rem;
}

.foot {
  position: relative;
  z-index: 1;
  margin-top: auto;
  border-top: 1px solid var(--line);
  background: color-mix(in srgb, var(--bg-elev) 92%, var(--bg));
}

.foot-inner {
  max-width: 68rem;
  margin: 0 auto;
  padding: 1.15rem 1.5rem 1.75rem;
}

.foot-line {
  margin: 0;
  font-size: 0.8rem;
  color: var(--muted-soft);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.foot-brand {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 700;
  color: var(--fg);
}

.foot-sep {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--line-strong);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
