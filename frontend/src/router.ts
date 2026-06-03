import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import TradingView from './views/TradingView.vue'
import WorkflowView from './views/WorkflowView.vue'
import ShortAnalysisView from './views/ShortAnalysisView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/trading', name: 'trading', component: TradingView },
    { path: '/workflow', name: 'workflow', component: WorkflowView },
    { path: '/analysis', name: 'ShortAnalysis', component: ShortAnalysisView },
  ],
})

export default router
