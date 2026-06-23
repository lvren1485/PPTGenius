<script setup lang="ts">
import { Download } from '@element-plus/icons-vue'

defineProps<{
  title: string
  meta: string[]
  tags: { label: string; type: string }[]
  date: string
  to: string
  downloading?: boolean
}>()

defineEmits<{ download: [e: Event] }>()
</script>

<template>
  <div class="card" @click="$router.push(to)">
    <div class="card-body">
      <strong class="card-title">{{ title }}</strong>
      <div class="card-meta">
        <span v-for="m in meta" :key="m">{{ m }}</span>
        <el-tag v-for="t in tags" :key="t.label" size="small" :type="t.type as any">{{ t.label }}</el-tag>
      </div>
    </div>
    <div class="card-right">
      <el-button :icon="Download" size="small" circle :loading="downloading" @click="$emit('download', $event)" />
      <span class="card-date">{{ date }}</span>
    </div>
  </div>
</template>

<style scoped>
.card {
  background: var(--bg-card); padding: 22px 28px; border-radius: var(--radius); cursor: pointer;
  display: flex; align-items: center; justify-content: space-between;
  border: 1px solid var(--border); transition: box-shadow .2s, border-color .2s;
}
.card:hover { box-shadow: var(--shadow-md); border-color: var(--primary-border); }
.card-body { display: flex; flex-direction: column; gap: 8px; }
.card-title { font-size: 16px; }
.card-meta { display: flex; align-items: center; gap: 12px; font-size: 14px; color: var(--text-secondary); }
.card-right { display: flex; align-items: center; gap: 16px; }
.card-date { font-size: 14px; color: var(--text-muted); white-space: nowrap; }
</style>
