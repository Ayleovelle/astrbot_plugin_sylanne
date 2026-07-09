import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'
import router from './router'
import { setUnauthorizedHandler } from './api/client'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// A 401 anywhere -> hard logout + back to login (matches the old UI's behavior).
setUnauthorizedHandler(() => {
  useAuthStore().logout()
  void router.replace({ name: 'login' })
})

app.mount('#app')
