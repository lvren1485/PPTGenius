<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import EmptyState from '../components/common/EmptyState.vue'

const router = useRouter()
const auth = useAuthStore()
const days = ref(30)
const summary = ref<any>(null)
const byDate = ref<any[]>([])
const byConv = ref<any[]>([])
const loading = ref(true)

onMounted(() => fetchAll())

async function fetchAll() {
  loading.value = true
  try {
    const [s, d, c] = await Promise.all([
      api.get('/cost/summary', { params: { user_id: auth.userId, days: days.value } }),
      api.get('/cost/by-date', { params: { user_id: auth.userId, days: days.value } }),
      api.get('/cost/by-conversation', { params: { user_id: auth.userId, days: days.value } }),
    ])
    if (s.data.code === 0) summary.value = s.data.data
    if (d.data.code === 0) byDate.value = d.data.data.items || []
    if (c.data.code === 0) byConv.value = c.data.data.items || []
  } finally {
    loading.value = false
  }
}

function goChat(cid: number) {
  router.push(`/chat/${cid}`)
}
</script>

<template>
  <div class="cost-page">
    <div class="cp-header">
      <h2>费用统计</h2>
      <el-select v-model="days" @change="fetchAll" style="width:120px">
        <el-option :value="7" label="最近 7 天" />
        <el-option :value="30" label="最近 30 天" />
        <el-option :value="90" label="最近 90 天" />
      </el-select>
    </div>

    <el-skeleton :loading="loading" :count="4" animated />
    <template v-if="!loading">
      <!-- Summary -->
      <el-row v-if="summary" :gutter="16" class="summary-row">
        <el-col :span="6">
          <el-statistic title="总费用" :value="Number(summary.total_cost || 0)" prefix="¥" :precision="4" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="会话数" :value="summary.total_conversations || 0" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="消息数" :value="summary.total_messages || 0" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="日均" :value="Number(summary.avg_cost_per_day || 0)" prefix="¥" :precision="4" />
        </el-col>
      </el-row>

      <!-- By Date -->
      <h3 class="section-title">按日期</h3>
      <el-table v-if="byDate.length" :data="byDate" stripe size="small" style="width:fit-content">
        <el-table-column prop="date" label="日期" width="200" />
        <el-table-column prop="cost" label="费用" width="200">
          <template #default="{ row }">¥{{ Number(row.cost).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column prop="conversations" label="会话数" width="200" />
        <el-table-column prop="messages" label="消息数" width="200" />
      </el-table>

      <!-- By Conversation -->
      <h3 class="section-title">按会话</h3>
      <el-table v-if="byConv.length" :data="byConv" stripe size="small" style="width:100%">
        <el-table-column prop="title" label="标题" min-width="200">
          <template #default="{ row }">
            <el-button link type="primary" @click="goChat(row.conversation_id)">
              {{ row.title || '未命名' }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="cost" label="费用" width="120">
          <template #default="{ row }">¥{{ Number(row.cost).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column prop="message_count" label="消息数" width="100" />
        <el-table-column label="时间" width="120">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleDateString('zh-CN') }}
          </template>
        </el-table-column>
      </el-table>

      <EmptyState v-if="!summary" description="暂无费用数据" />
    </template>
  </div>
</template>

<style scoped>
.cost-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}
.cp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
.summary-row {
  margin-bottom: 32px;
}
.section-title {
  font-size: 16px;
  margin: 24px 0 12px;
  color: #606266;
}
</style>
