import { ref, watch } from 'vue'

const THEME_KEY = 'myscript-theme'
const MODES = ['system', 'light', 'dark']
const ICONS = { system: '💻', light: '☀️', dark: '🌙' }

function applyTheme(mode) {
  const el = document.documentElement
  if (mode === 'light') {
    el.setAttribute('data-theme', 'light')
  } else if (mode === 'dark') {
    el.setAttribute('data-theme', 'dark')
  } else {
    el.removeAttribute('data-theme')
  }
  localStorage.setItem(THEME_KEY, mode)
}

export function useTheme() {
  const mode = ref(localStorage.getItem(THEME_KEY) || 'system')

  watch(mode, applyTheme, { immediate: true })

  function cycleTheme() {
    const next = (MODES.indexOf(mode.value) + 1) % MODES.length
    mode.value = MODES[next]
  }

  return { mode, cycleTheme, themeIcon: ICONS }
}
