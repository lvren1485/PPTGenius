<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

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
      <el-button text @click="handleLogout">登出</el-button>
    </div>
  </el-header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fafbfc;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 24px;
  height: 56px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 32px;
}
.logo {
  font-size: 18px;
  font-weight: 700;
  color: #409eff;
  cursor: pointer;
  white-space: nowrap;
}
.nav-links {
  display: flex;
  align-items: center;
  gap: 4px;
}
.nav-item {
  padding: 8px 16px;
  text-decoration: none;
  color: #606266;
  border-radius: 4px;
  font-size: 14px;
  transition: background .2s, color .2s;
}
.nav-item:hover {
  background: #f5f7fa;
  color: #409eff;
}
.nav-item.active {
  color: #409eff;
  background: #ecf5ff;
}
.header-right {
  display: flex;
  align-items: center;
}
</style>
