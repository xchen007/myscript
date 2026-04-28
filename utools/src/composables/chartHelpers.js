/** Shared constants and helpers for Jira chart components */

export const PALETTE = [
  '#58a6ff', '#f0883e', '#3fb950', '#d2a8ff',
  '#f778ba', '#79c0ff', '#ffd33d', '#ff7b72',
]

export function fmtH(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}

export function shortLabel(label, max = 20) {
  return label.length > max ? label.slice(0, max - 2) + '…' : label
}
