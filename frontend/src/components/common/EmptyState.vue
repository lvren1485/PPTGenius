<script setup lang="ts">
defineProps<{ description?: string }>()
</script>

<template>
  <div class="empty-state">
    <el-empty :description="description || '暂无数据'" />
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}
</style>
