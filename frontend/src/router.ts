import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import TradingView from './views/TradingView.vue'
import WorkflowView from './views/WorkflowView.vue'
import ShortsView from './views/ShortsView.vue'
import SettingsView from './views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/trading', name: 'trading', component: TradingView },
    { path: '/workflow', name: 'workflow', component: WorkflowView },
    { path: '/analysis', name: 'shorts', component: ShortsView },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})

export default router
