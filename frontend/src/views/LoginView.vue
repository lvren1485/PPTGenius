<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const form = ref({ name: '', password: '' })
const remember = ref(false)
const loading = ref(false)

async function handleLogin() {
  loading.value = true
  try {
    const { data } = await api.post('/auth/login', form.value)
    if (data.code === 0) {
      auth.setAuth(data.data.token, data.data.user_id, data.data.name, remember.value)
      router.push('/')
    }
  } catch (e: any) {
    const msg = e.response?.data?.detail?.message || '登录失败'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <template #header>
        <h2>PPTGenius</h2>
        <p class="subtitle">AI PPT 生成平台</p>
      </template>
      <el-form @submit.prevent="handleLogin" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="form.name" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="remember">记住我（7天内自动登录）</el-checkbox>
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" block>
          登 录
        </el-button>
      </el-form>
      <p class="switch-link">
        没有账号？<router-link to="/register">去注册 →</router-link>
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.auth-card {
  width: 400px;
}
.auth-card h2 {
  text-align: center;
  margin-bottom: 4px;
}
.subtitle {
  text-align: center;
  color: #909399;
  font-size: 14px;
}
.switch-link {
  text-align: center;
  margin-top: 16px;
  font-size: 14px;
  color: #909399;
}
</style>
