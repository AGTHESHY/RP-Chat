import { createApp } from 'vue'
import { ElMessage } from 'element-plus'
import App from './App.vue'
import router from './router'
import { setupElMessageBehavior } from './utils/message'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/message/style/css'
import './styles/global.css'
import './styles/layout.css'

setupElMessageBehavior()

router.onError((error, to) => {
  const message = error instanceof Error ? error.message : String(error)
  if (
    message.includes('Failed to fetch dynamically imported module')
    || message.includes('Importing a module script failed')
  ) {
    ElMessage.error('页面脚本加载失败，正在刷新…')
    window.location.href = to.fullPath
    return
  }
  console.error(error)
})

createApp(App).use(router).mount('#app')
