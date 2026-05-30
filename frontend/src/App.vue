<script setup lang="ts">
import AppHeader from './components/layout/AppHeader.vue'
</script>

<template>
  <AppHeader v-if="$route.meta.showHeader !== false" />
  <router-view />
</template>
