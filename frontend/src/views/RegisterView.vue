<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const form = ref({ name: '', password: '', confirmPassword: '' })
const loading = ref(false)

async function handleRegister() {
  if (form.value.password !== form.value.confirmPassword) {
    ElMessage.error('两次密码不一致')
    return
  }
  loading.value = true
  try {
    const { data } = await api.post('/auth/register', {
      name: form.value.name,
      password: form.value.password,
    })
    if (data.code === 0) {
      auth.setAuth(data.data.token, data.data.user_id, data.data.name)
      router.push('/')
    }
  } catch (e: any) {
    const msg = e.response?.data?.detail?.message || '注册失败'
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
        <h2>创建账号</h2>
        <p class="subtitle">加入 PPTGenius</p>
      </template>
      <el-form @submit.prevent="handleRegister" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="form.name" placeholder="2-64 个字符" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="form.confirmPassword" type="password" show-password placeholder="再次输入密码" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" block>
          注 册
        </el-button>
      </el-form>
      <p class="switch-link">
        已有账号？<router-link to="/login">去登录 →</router-link>
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
