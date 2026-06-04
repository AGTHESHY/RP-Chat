<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const active = computed(() => route.path)

function navigate(path: string) {
  router.push(path)
}
</script>

<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="brand">RP Chat 提示词管理</div>
      <el-menu
        mode="horizontal"
        :default-active="active"
        :ellipsis="false"
        class="nav-menu"
        @select="navigate"
      >
        <el-menu-item index="/">提示词管理</el-menu-item>
        <el-menu-item index="/test-cases">测试用例</el-menu-item>
        <el-menu-item index="/jailbreak">破限管理</el-menu-item>
        <el-menu-item index="/test">RP 测试</el-menu-item>
        <el-menu-item index="/rp-eval">RP 测评</el-menu-item>
        <el-menu-item index="/smart-brain">智脑</el-menu-item>
        <el-menu-item index="/api-config">API 配置</el-menu-item>
      </el-menu>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.app-layout {
  height: 100vh;
  min-height: 100vh;
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.app-main {
  flex: 1;
  min-height: 0;
  padding: 16px 24px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.app-main > * {
  flex: 1;
  min-height: 0;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  padding: 0 24px;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}

.app-header::-webkit-scrollbar {
  display: none;
}

.brand {
  font-size: 18px;
  font-weight: 600;
  white-space: nowrap;
}

.nav-menu {
  flex: 1;
  min-width: 0;
  border-bottom: none;
}
</style>
