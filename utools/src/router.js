import { createRouter, createWebHashHistory } from 'vue-router'
import BisyncPanel    from './components/bisync/BisyncPanel.vue'
import JiratoolsPanel from './components/jiratools/JiratoolsPanel.vue'
import Sync2podPanel  from './components/sync2pod/Sync2podPanel.vue'

const routes = [
  { path: '/',         redirect: '/bisync' },
  { path: '/bisync',   component: BisyncPanel },
  { path: '/jira',     component: JiratoolsPanel },
  { path: '/sync2pod', component: Sync2podPanel },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
