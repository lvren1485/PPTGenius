import { createRouter, createWebHistory } from 'vue-router'
import { h } from 'vue'
import { useAuthStore } from '../stores/auth'

const TestPage = { template: '<div style="padding:40px"><h2>Test Page Works</h2></div>' }

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/LoginView.vue'),
      meta: { showHeader: false },
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('../views/RegisterView.vue'),
      meta: { showHeader: false },
    },
    {
      path: '/',
      name: 'Home',
      component: () => import('../views/HomeView.vue'),
    },
    {
      path: '/chat/:id',
      name: 'Chat',
      component: () => import('../views/ChatView.vue'),
    },
    {
      path: '/outlines',
      name: 'OutlineList',
      component: () => import('../views/OutlineListView.vue'),
    },
    {
      path: '/outline/:id',
      name: 'OutlineDetail',
      component: () => import('../views/OutlineDetail.vue'),
    },
    {
      path: '/presentations',
      name: 'PptList',
      component: () => import('../views/PptListView.vue'),
    },
    {
      path: '/ppt/:id',
      name: 'PptDetail',
      component: () => import('../views/PptDetail.vue'),
    },
    {
      path: '/cost',
      name: 'Cost',
      component: () => import('../views/CostView.vue'),
    },
    {
      path: '/snapshot/:id',
      name: 'SnapshotDetail',
      component: () => import('../views/SnapshotDetail.vue'),
    },
    {
      path: '/knowledge',
      name: 'Knowledge',
      component: () => import('../views/KnowledgeView.vue'),
    },
    {
      path: '/test-page',
      name: 'TestPage',
      component: TestPage,
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  const isPublic = to.name === 'Login' || to.name === 'Register'
  if (!auth.isLoggedIn && !isPublic) return next('/login')
  if (auth.isLoggedIn && isPublic) return next('/')
  next()
})

export default router
