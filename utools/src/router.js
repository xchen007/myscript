import { createRouter, createWebHistory } from 'vue-router'
import BisyncPanel    from './components/bisync/BisyncPanel.vue'
import JiratoolsPanel from './components/jiratools/JiratoolsPanel.vue'
import Sync2podPanel  from './components/sync2pod/Sync2podPanel.vue'
import SettingsPanel  from './components/settings/SettingsPanel.vue'

const routes = [
  { path: '/',         redirect: '/bisync' },
  { path: '/bisync',   component: BisyncPanel },
  { path: '/jira',     component: JiratoolsPanel },
  { path: '/sync2pod', component: Sync2podPanel },
  { path: '/settings', component: SettingsPanel },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
