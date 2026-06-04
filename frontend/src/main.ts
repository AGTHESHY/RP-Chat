import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './styles/global.css'
import './styles/layout.css'

createApp(App).use(router).mount('#app')
