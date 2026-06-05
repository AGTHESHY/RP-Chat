import { createRouter, createWebHistory } from 'vue-router'
import PromptManager from '../views/PromptManager.vue'
import TestPage from '../views/TestPage.vue'
import RpEvalPage from '../views/RpEvalPage.vue'
import SmartBrainPage from '../views/SmartBrainPage.vue'
import ApiConfigPage from '../views/ApiConfigPage.vue'
import JailbreakPage from '../views/JailbreakPage.vue'
import TestCasePage from '../views/TestCasePage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'prompts',
      component: PromptManager,
    },
    {
      path: '/test',
      name: 'test',
      component: TestPage,
    },
    {
      path: '/rp-eval',
      name: 'rp-eval',
      component: RpEvalPage,
    },
    {
      path: '/smart-brain',
      name: 'smart-brain',
      component: SmartBrainPage,
    },
    {
      path: '/api-config',
      name: 'api-config',
      component: ApiConfigPage,
    },
    {
      path: '/jailbreak',
      name: 'jailbreak',
      component: JailbreakPage,
    },
    {
      path: '/test-cases',
      name: 'test-cases',
      component: TestCasePage,
    },
  ],
})

export default router
