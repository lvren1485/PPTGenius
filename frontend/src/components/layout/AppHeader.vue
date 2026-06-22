<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { Sunny, Moon } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const isDark = ref(false)

onMounted(() => {
  isDark.value = localStorage.getItem('theme') === 'dark'
  applyTheme()
})

function toggleTheme() {
  isDark.value = !isDark.value
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
  applyTheme()
}

function applyTheme() {
  document.documentElement.classList.toggle('dark', isDark.value)
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

const navItems = [
  { path: '/', label: '首页' },
  { path: '/outlines', label: '大纲' },
  { path: '/presentations', label: 'PPT' },
  { path: '/cost', label: '费用' },
  { path: '/knowledge', label: '知识库' },
]
</script>

<template>
  <el-header class="app-header">
    <div class="header-left">
      <span class="logo" @click="router.push('/')">PPTGenius</span>
      <nav class="nav-links">
        <template v-for="item in navItems" :key="item.path">
          <router-link
            :to="item.path"
            class="nav-item"
            :class="{ active: route.path === item.path || route.path.startsWith(item.path + '/') }"
          >
            {{ item.label }}
          </router-link>
        </template>
      </nav>
    </div>
    <div class="header-right">
      <el-button text :icon="isDark ? Sunny : Moon" @click="toggleTheme" title="切换主题" />
      <el-button text @click="handleLogout">登出</el-button>
    </div>
  </el-header>
</template>

<style scoped>
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bg-card); border-bottom: 1px solid var(--border);
  padding: 0 24px; height: 56px; transition: background .3s;
}
.header-left { display: flex; align-items: center; gap: 32px; }
.logo {
  font-size: 18px; font-weight: 800; cursor: pointer; white-space: nowrap;
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
.nav-links { display: flex; align-items: center; gap: 2px; }
.nav-item {
  padding: 8px 16px; text-decoration: none; color: var(--text-secondary);
  border-radius: var(--radius-sm); font-size: 14px; font-weight: 500;
  transition: background .2s, color .2s;
}
.nav-item:hover { background: var(--bg-hover); color: var(--primary); }
.nav-item.active { color: var(--primary); background: var(--primary-bg); }
.header-right { display: flex; align-items: center; gap: 4px; }
</style>
