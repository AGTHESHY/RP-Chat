import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'prompts',
      component: () => import('../views/PromptManager.vue'),
    },
    {
      path: '/test',
      name: 'test',
      component: () => import('../views/TestPage.vue'),
    },
    {
      path: '/rp-eval',
      name: 'rp-eval',
      component: () => import('../views/RpEvalPage.vue'),
    },
    {
      path: '/api-config',
      name: 'api-config',
      component: () => import('../views/ApiConfigPage.vue'),
    },
    {
      path: '/jailbreak',
      name: 'jailbreak',
      component: () => import('../views/JailbreakPage.vue'),
    },
    {
      path: '/test-cases',
      name: 'test-cases',
      component: () => import('../views/TestCasePage.vue'),
    },
  ],
})

export default router
