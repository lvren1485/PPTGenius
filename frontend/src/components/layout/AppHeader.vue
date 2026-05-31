<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const auth = useAuthStore()

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-header class="app-header">
    <div class="header-left">
      <span class="logo" @click="router.push('/')">PPTGenius</span>
      <el-menu
        mode="horizontal"
        :default-active="$route.path"
        :ellipsis="false"
        @select="(k: string) => router.push(k)"
      >
        <el-menu-item index="/">首页</el-menu-item>
        <el-sub-menu index="works">
          <template #title>作品</template>
          <el-menu-item index="/outlines">大纲列表</el-menu-item>
          <el-menu-item index="/presentations">PPT 列表</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/cost">费用</el-menu-item>
        <el-menu-item index="/knowledge">知识库</el-menu-item>
      </el-menu>
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
  background: #fff;
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
.header-right {
  display: flex;
  align-items: center;
}
.el-menu {
  border-bottom: none;
}
</style>
