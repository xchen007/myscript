<template>
  <div class="ticket-table" @click="closeDd">
    <!-- ── Table ──────────────────────────────────────────────────────── -->
    <div class="table-wrap">
      <!-- Stats bar inside table-wrap for clean boundary -->
      <div class="stats-bar" v-if="data.stats?.total_tickets > 0">
        <span class="stat"><b>{{ data.stats.total_tickets }}</b> tickets</span>
        <template v-for="[st, cnt] in sortedStatusCounts" :key="st">
          <span class="sep">·</span>
          <span class="stat"><span :class="statusDotCls(st)" class="sdot" /><b>{{ cnt }}</b> {{ st }}</span>
        </template>
        <template v-if="data.stats.total_points > 0">
          <span class="sep">·</span>
          <span class="stat"><b>{{ data.stats.total_points }}</b> pts</span>
        </template>
        <span class="sep">·</span>
        <span class="stat"><b>{{ fmtSeconds(data.stats.total_log_seconds) }}</b> logged</span>
        <span v-if="agoText" class="ago-hint">{{ agoText }}</span>
        <span class="spacer" />
        <span class="meta-label">{{ data.meta?.label }} · {{ data.meta?.user }}</span>
      </div>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th class="th-exp" />
              <th
                v-for="col in orderedColumns"
                :key="col.id"
                v-show="colVis[col.id]"
                :class="[cellClass(col.id), { sortable: !!col.sortKey, 'drag-over': dropTarget === col.id }]"
                :title="col.title || col.label"
                draggable="true"
                @dragstart="onDragStart($event, col.id)"
                @dragover="onDragOver($event, col.id)"
                @drop="onDrop($event, col.id)"
                @dragend="onDragEnd"
                @click="handleHeaderClick(col.sortKey, $event)"
              >
                {{ col.label }}
                <span v-if="getSortState(col.sortKey)" class="sort-ind">
                  {{ getSortState(col.sortKey).dir === 'asc' ? '↑' : '↓' }}
                  <span v-if="sorting.length > 1" class="sort-ord">{{ getSortState(col.sortKey).order }}</span>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in displayRows" :key="row.key">
              <tr
                :class="{ expanded: expandedRows.has(row.key) }"
                @click.stop="toggleRow(row.key)"
              >
                <td class="td-exp">
                  <span class="exp-arrow" :class="{ open: expandedRows.has(row.key) }">▶</span>
                </td>
                <td
                  v-for="col in orderedColumns"
                  :key="col.id"
                  v-show="colVis[col.id]"
                  :class="cellClass(col.id)"
                  :title="col.id === 'summary' ? row.summary : undefined"
                >
                  <template v-if="col.id === 'key'">
                    <a class="ticket-key" href="#" @click.prevent.stop="openUrl(row.url)">{{ row.key }}</a>
                  </template>
                  <template v-else-if="col.id === 'project'">
                    <span class="project-tag">{{ row.project ?? row.key.rsplit?.('-', 1)[0] ?? '—' }}</span>
                  </template>
                  <template v-else-if="col.id === 'summary'">
                    <span class="summary-text">{{ row.summary }}</span>
                  </template>
                  <template v-else-if="col.id === 'type'">
                    <span :class="typeCls(row.type)" class="badge">{{ typeIcon(row.type) }}{{ row.type }}</span>
                  </template>
                  <template v-else-if="col.id === 'status'">
                    <span :class="statusCls(row.status)" class="badge">{{ statusIcon(row.status) }}{{ row.status }}</span>
                  </template>
                  <template v-else-if="col.id === 'priority'">
                    <span :class="priorityCls(row.priority)" class="badge">{{ priorityIcon(row.priority) }}{{ row.priority }}</span>
                  </template>
                  <template v-else-if="col.id === 'points'">
                    <span :class="{ 'pts-val': row.points != null }">{{ row.points ?? '—' }}</span>
                  </template>
                  <template v-else-if="col.id === 'assignee'">{{ row.assignee || '—' }}</template>
                  <template v-else-if="col.id === 'estimated'">{{ fmtSeconds(row.estimated_seconds) }}</template>
                  <template v-else-if="col.id === 'logged'">{{ fmtSeconds(row.log_seconds) }}</template>
                  <template v-else-if="col.id === 'done_label'">{{ row.done_label || '—' }}</template>
                  <template v-else-if="col.id === 'labels'">
                    <span class="label-tags">
                      <span v-for="lbl in filteredLabels(row.labels)" :key="lbl" class="label-tag">{{ lbl }}</span>
                      <span v-if="!filteredLabels(row.labels).length">—</span>
                    </span>
                  </template>
                </td>
              </tr>

              <!-- Detail row -->
              <tr v-if="expandedRows.has(row.key)" class="detail-tr">
                <td :colspan="visibleColCount" style="padding:0">
                  <div class="detail-panel">
                    <div class="detail-body">
                      <div class="detail-grid">
                        <div class="di">
                          <div class="dv badge-row">
                            <span :class="statusCls(row.status)" class="badge">{{ statusIcon(row.status) }}{{ row.status }}</span>
                            <span :class="priorityCls(row.priority)" class="badge">{{ priorityIcon(row.priority) }}{{ row.priority }}</span>
                            <span :class="typeCls(row.type)" class="badge">{{ typeIcon(row.type) }}{{ row.type }}</span>
                          </div>
                        </div>
                        <div class="di">
                          <div class="dl">负责人</div>
                          <div class="dv">{{ row.assignee || '—' }}</div>
                        </div>
                        <div class="di">
                          <div class="dl">Story Points</div>
                          <div class="dv mono">{{ row.points ?? '— (未估算)' }}</div>
                        </div>
                        <div class="di full title-row">
                          <a v-if="row.url" href="#" class="detail-key" @click.prevent.stop="openUrl(row.url)">{{ row.key }} ↗</a>
                          <span v-else class="detail-key">{{ row.key }}</span>
                          <span class="detail-summary">{{ row.summary }}</span>
                        </div>
                        <div class="di full">
                          <div class="dl">Description</div>
                          <!-- eslint-disable-next-line vue/no-v-html -->
                          <div class="dv desc-text" v-html="formatDesc(row.description)" />
                        </div>
                      </div>

                      <!-- Time Tracking sidebar -->
                      <div class="time-track">
                        <div class="tt-heading">⏱ TIME TRACKING</div>
                        <div class="tt-row">
                          <div class="tt-label">Estimated</div>
                          <div class="tt-bar"><div class="tt-fill tt-est" style="width:100%"></div></div>
                          <div class="tt-val">{{ fmtSeconds(row.estimated_seconds) || '—' }}</div>
                        </div>
                        <div class="tt-row">
                          <div class="tt-label">Remaining</div>
                          <div class="tt-bar"><div class="tt-fill tt-rem" :style="{ width: remainPct(row) + '%' }"></div></div>
                          <div class="tt-val">{{ fmtSeconds(Math.max(0, row.estimated_seconds - row.log_seconds)) || '—' }}</div>
                        </div>
                        <div class="tt-row">
                          <div class="tt-label">Logged</div>
                          <div class="tt-bar"><div class="tt-fill tt-log" :style="{ width: logPct(row) + '%' }"></div></div>
                          <div class="tt-val">{{ fmtSeconds(row.log_seconds) || '—' }}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>

            <tr v-if="!displayRows.length">
              <td :colspan="visibleColCount" class="empty-cell">{{ emptyMessage }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Footer -->
      <div class="table-footer" @click.stop>
        <!-- Multi-select chip filters -->
        <div v-for="fd in FILTER_DEFS" :key="fd.key" class="chip-filter" :class="{ open: openDd === fd.key }">
          <span class="cf-label" @click.stop="toggleDd(fd.key)">{{ fd.label }}</span>
          <span v-if="!dropFilters[fd.key].length" class="cf-all" @click.stop="toggleDd(fd.key)">All</span>
          <span
            v-for="val in dropFilters[fd.key]"
            :key="val"
            class="cf-chip"
          >{{ val }}<button class="cf-chip-rm" @click.stop="removeChip(fd.key, val)">×</button></span>
          <button v-if="dropFilters[fd.key].length" class="cf-clear" @click.stop="clearFilter(fd.key)">×</button>
          <button class="cf-toggle" @click.stop="toggleDd(fd.key)">▾</button>

          <!-- Dropdown (opens upward) -->
          <div class="cf-dd cf-dd-up" v-show="openDd === fd.key" @click.stop>
            <!-- Search input -->
            <div class="cf-dd-search">
              <span class="cf-dd-search-icon">🔍</span>
              <input
                v-model="ddSearch[fd.key]"
                class="cf-dd-search-input"
                placeholder="Search…"
                @click.stop
              />
            </div>
            <div class="cf-dd-sep" />
            <div
              class="cf-dd-item cf-dd-sel"
              @click="toggleAllFilter(fd.key, fd.options())"
            >
              <span class="cf-ck" :class="{ on: dropFilters[fd.key].length === fd.options().length && fd.options().length > 0, half: dropFilters[fd.key].length > 0 && dropFilters[fd.key].length < fd.options().length }">
                {{ dropFilters[fd.key].length === fd.options().length && fd.options().length > 0 ? '✓' : dropFilters[fd.key].length > 0 ? '−' : '' }}
              </span>
              {{ dropFilters[fd.key].length ? `Selected (${dropFilters[fd.key].length})` : 'All' }}
            </div>
            <div class="cf-dd-sep" />
            <div
              v-for="opt in filteredOpts(fd)"
              :key="opt"
              class="cf-dd-item"
              @click="toggleFilter(fd.key, opt)"
            >
              <span class="cf-ck" :class="{ on: dropFilters[fd.key].includes(opt) }">
                {{ dropFilters[fd.key].includes(opt) ? '✓' : '' }}
              </span>
              {{ opt }}
            </div>
            <div v-if="filteredOpts(fd).length === 0" class="cf-dd-empty">No match</div>
          </div>
        </div>

        <span class="sort-hint"><kbd>Shift</kbd>+Click 多列排序</span>

        <!-- Sort pills -->
        <div class="sort-pills">
          <div v-for="s in sorting" :key="s.col" class="sort-pill">
            {{ colLabel(s.col) }} {{ s.dir === 'asc' ? '↑' : '↓' }}
            <span class="pill-x" @click.stop="removeSortCol(s.col)">✕</span>
          </div>
        </div>

        <div class="spacer" />

        <!-- Column visibility -->
        <div class="dropdown col-dd">
          <button class="btn" :class="{ active: hiddenCount > 0 }" @click.stop="toggleDd('cols')">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M2 2h3v12H2V2zm4 0h3v12H6V2zm4 0h4v12h-4V2z"/></svg>
            Columns{{ hiddenCount > 0 ? ` (${hiddenCount})` : '' }}
          </button>
          <div class="dd-menu col-menu col-menu-up" v-show="openDd === 'cols'" @click.stop>
            <div class="col-actions">
              <span @click="toggleAllCols(true)">全部显示</span>
              <span @click="toggleAllCols(false)">全部隐藏</span>
            </div>
            <div class="col-divider" />
            <label
              v-for="col in orderedColumns"
              :key="col.id"
              class="col-item"
              @click.stop="toggleCol(col.id)"
            >
              <span class="tog-box" :class="{ on: colVis[col.id] }">{{ colVis[col.id] ? '✓' : '' }}</span>
              {{ col.title || col.label }}
            </label>
          </div>
        </div>

        <div class="row-count">
          {{ displayRows.length < (data.stats?.total_tickets ?? 0)
            ? `显示 ${displayRows.length} / ${data.stats.total_tickets} 条`
            : `共 ${data.stats?.total_tickets ?? displayRows.length} 条` }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'

const props = defineProps({
  data: { type: Object, required: true },
  appState: { type: String, default: 'idle' },
  labelFilter: { type: String, default: '' },
  prefKey: { type: String, default: 'sprint-table-prefs:v2' },
  agoText: { type: String, default: '' },
})

const PREF_KEY_REF = computed(() => props.prefKey)

// ── Column definitions ───────────────────────────────────────────────────────
const COLUMNS = [
  { id: 'key',       label: 'Key',       sortKey: 'key' },
  { id: 'project',   label: 'Project',   sortKey: 'project' },
  { id: 'summary',   label: 'Summary',   sortKey: 'summary' },
  { id: 'type',      label: 'Type',      sortKey: 'type_rank' },
  { id: 'status',    label: 'Status',    sortKey: 'status_rank' },
  { id: 'priority',  label: 'Priority',  sortKey: 'priority_rank' },
  { id: 'labels',    label: 'Labels',    sortKey: null },
  { id: 'points',    label: 'Pts',       sortKey: 'points',             title: 'Story Points' },
  { id: 'assignee',  label: 'Assignee',  sortKey: 'assignee' },
  { id: 'estimated', label: 'Est.',      sortKey: 'estimated_seconds',  title: 'Estimated Time' },
  { id: 'logged',    label: 'Log',       sortKey: 'log_seconds',        title: 'Logged Time' },
  { id: 'done_label',label: 'Done',      sortKey: null },
]

// ── State ────────────────────────────────────────────────────────────────────
const DEFAULT_HIDDEN = new Set(['done_label', 'project', 'labels'])
const sorting      = ref([])   // [{ col: sortKey, dir: 'asc'|'desc' }]
const colVis = reactive(Object.fromEntries(
  COLUMNS.map(c => [c.id, !DEFAULT_HIDDEN.has(c.id)])
))

// If labelFilter is provided, default labels column to visible
if (props.labelFilter !== undefined && props.labelFilter !== '') {
  colVis.labels = true
}
const colOrder     = ref(COLUMNS.map(c => c.id))
const expandedRows = ref(new Set())
const dropFilters  = reactive({ type: [], status: [], priority: [], assignee: [] })
const openDd       = ref('')
const ddSearch     = reactive({ type: '', status: '', priority: '', assignee: '' })

const orderedColumns = computed(() =>
  colOrder.value
    .map(id => COLUMNS.find(c => c.id === id))
    .filter(Boolean)
)

// ── Persistence ──────────────────────────────────────────────────────────────
function loadPrefs() {
  const saved = window.myscriptAPI?.getPref(PREF_KEY_REF.value) ?? {}
  if (Array.isArray(saved.sorting))     sorting.value = saved.sorting
  if (saved.colVis)                     Object.assign(colVis, saved.colVis)
  if (saved.dropFilters) {
    for (const k of Object.keys(dropFilters)) {
      const v = saved.dropFilters[k]
      const arr = Array.isArray(v) ? v : (v ? [v] : [])
      dropFilters[k].splice(0, Infinity, ...arr)
    }
  }
  if (Array.isArray(saved.colOrder)) {
    // Merge: use saved order, append any new columns not in saved list
    const known = new Set(saved.colOrder)
    const merged = [...saved.colOrder.filter(id => COLUMNS.some(c => c.id === id))]
    for (const c of COLUMNS) { if (!known.has(c.id)) merged.push(c.id) }
    colOrder.value = merged
  }
}

function savePrefs() {
  window.myscriptAPI?.setPref(PREF_KEY_REF.value, {
    sorting:     sorting.value,
    colVis:      { ...colVis },
    colOrder:    colOrder.value,
    dropFilters: Object.fromEntries(Object.keys(dropFilters).map(k => [k, [...dropFilters[k]]])),
  })
}

// ── Filter options (derived from data) ───────────────────────────────────────
const typeOptions = computed(() => {
  const m = {}
  props.data.tickets?.forEach(t => { if (!(t.type in m)) m[t.type] = t.type_rank })
  return Object.entries(m).sort((a, b) => a[1] - b[1]).map(e => e[0])
})
const statusOptions = computed(() => {
  const m = {}
  props.data.tickets?.forEach(t => { if (!(t.status in m)) m[t.status] = t.status_rank })
  return Object.entries(m).sort((a, b) => a[1] - b[1]).map(e => e[0])
})
const priorityOptions = computed(() => {
  const m = {}
  props.data.tickets?.forEach(t => { if (!(t.priority in m)) m[t.priority] = t.priority_rank })
  return Object.entries(m).sort((a, b) => a[1] - b[1]).map(e => e[0])
})
const assigneeOptions = computed(() => {
  const s = new Set()
  props.data.tickets?.forEach(t => { if (t.assignee) s.add(t.assignee) })
  return [...s].sort()
})

const FILTER_DEFS = computed(() => [
  { key: 'type',     label: 'Type',     options: () => typeOptions.value,     badgeCls: typeCls,     badgeIcon: typeIcon },
  { key: 'status',   label: 'Status',   options: () => statusOptions.value,   badgeCls: statusCls,   badgeIcon: statusIcon },
  { key: 'priority', label: 'Priority', options: () => priorityOptions.value, badgeCls: priorityCls, badgeIcon: priorityIcon },
  { key: 'assignee', label: 'Assignee', options: () => assigneeOptions.value, badgeCls: () => '',    badgeIcon: () => '' },
])

// ── Derived rows (filtered + sorted) ─────────────────────────────────────────
const displayRows = computed(() => {
  let rows = props.data.tickets ?? []
  if (dropFilters.type.length)     rows = rows.filter(t => dropFilters.type.includes(t.type))
  if (dropFilters.status.length)   rows = rows.filter(t => dropFilters.status.includes(t.status))
  if (dropFilters.priority.length) rows = rows.filter(t => dropFilters.priority.includes(t.priority))
  if (dropFilters.assignee.length) rows = rows.filter(t => dropFilters.assignee.includes(t.assignee))
  if (sorting.value.length) {
    rows = [...rows].sort((a, b) => {
      for (const { col, dir } of sorting.value) {
        const va = a[col] ?? '', vb = b[col] ?? ''
        if (va < vb) return dir === 'asc' ? -1 : 1
        if (va > vb) return dir === 'asc' ? 1 : -1
      }
      return 0
    })
  }
  return rows
})

const visibleColCount = computed(() =>
  1 + COLUMNS.filter(c => colVis[c.id]).length
)
const hiddenCount = computed(() => COLUMNS.filter(c => !colVis[c.id]).length)

const emptyMessage = computed(() => {
  if (props.appState === 'loading') return '⏳ 正在查询…'
  if (props.appState === 'error')   return '❌ 查询出错，请查看日志'
  if (props.appState === 'no-data') return 'ℹ️ 未找到匹配的 Ticket'
  if (props.data.tickets?.length && displayRows.value.length === 0) return '没有匹配的 Ticket'
  return '填写上方表单后点击 Run'
})

// ── Stats bar helpers ─────────────────────────────────────────────────────────
const STATUS_RANK = { 'Open': 0, 'In Progress': 1, 'In Review': 2, 'Resolved': 3, 'Closed': 4, 'Done': 4 }
const sortedStatusCounts = computed(() =>
  Object.entries(props.data.stats?.status_counts ?? {})
    .sort((a, b) => (STATUS_RANK[a[0]] ?? 9) - (STATUS_RANK[b[0]] ?? 9))
    .filter(([, cnt]) => cnt > 0)
)

function statusDotCls(st) {
  return {
    'sdot-inprog':  st === 'In Progress',
    'sdot-review':  st === 'In Review',
    'sdot-reopen':  st === 'Reopened',
    'sdot-done':    st === 'Resolved' || st === 'Closed' || st === 'Done',
    'sdot-blocked': st === 'Blocked',
  }
}

// ── Sorting ───────────────────────────────────────────────────────────────────
function handleHeaderClick(sortKey, event) {
  if (!sortKey) return
  const isShift = event.shiftKey
  const idx = sorting.value.findIndex(s => s.col === sortKey)
  if (isShift) {
    const s = [...sorting.value]
    if (idx === -1)                s.push({ col: sortKey, dir: 'asc' })
    else if (s[idx].dir === 'asc') s[idx] = { col: sortKey, dir: 'desc' }
    else                           s.splice(idx, 1)
    sorting.value = s
  } else {
    if (idx === -1)                            sorting.value = [{ col: sortKey, dir: 'asc' }]
    else if (sorting.value[idx].dir === 'asc') sorting.value = [{ col: sortKey, dir: 'desc' }]
    else                                       sorting.value = []
  }
  savePrefs()
}

function getSortState(sortKey) {
  if (!sortKey) return null
  const item = sorting.value.find(s => s.col === sortKey)
  if (!item) return null
  return { dir: item.dir, order: sorting.value.indexOf(item) + 1 }
}

function removeSortCol(col) {
  sorting.value = sorting.value.filter(s => s.col !== col)
  savePrefs()
}

function colLabel(sortKey) {
  return COLUMNS.find(c => c.sortKey === sortKey)?.label ?? sortKey
}

// ── Row expansion ─────────────────────────────────────────────────────────────
function toggleRow(key) {
  const s = new Set(expandedRows.value)
  if (s.has(key)) s.delete(key); else s.add(key)
  expandedRows.value = s
}

// ── Dropdowns ─────────────────────────────────────────────────────────────────
function toggleDd(key) {
  if (openDd.value === key) { openDd.value = ''; ddSearch[key] = '' }
  else { openDd.value = key; ddSearch[key] = '' }
}
function closeDd() { if (openDd.value && ddSearch[openDd.value] !== undefined) ddSearch[openDd.value] = ''; openDd.value = '' }
function filteredOpts(fd) {
  const all = fd.options()
  const q = (ddSearch[fd.key] || '').toLowerCase()
  return q ? all.filter(o => o.toLowerCase().includes(q)) : all
}
function toggleFilter(field, val) {
  const arr = dropFilters[field]
  const idx = arr.indexOf(val)
  if (idx >= 0) arr.splice(idx, 1); else arr.push(val)
  savePrefs()
}
function clearFilter(field) { dropFilters[field].splice(0); savePrefs() }
function removeChip(field, val) {
  const idx = dropFilters[field].indexOf(val)
  if (idx >= 0) { dropFilters[field].splice(idx, 1); savePrefs() }
}
function toggleAllFilter(field, opts) {
  if (dropFilters[field].length === opts.length) {
    dropFilters[field].splice(0)
  } else {
    dropFilters[field].splice(0, Infinity, ...opts)
  }
  savePrefs()
}

function openUrl(url) {
  if (url) window.myscriptAPI?.openExternal(url)
}

function remainPct(row) {
  if (!row.estimated_seconds) return 0
  return Math.min(100, Math.max(0, (row.estimated_seconds - row.log_seconds) / row.estimated_seconds * 100))
}
function logPct(row) {
  if (!row.estimated_seconds) return 0
  return Math.min(100, row.log_seconds / row.estimated_seconds * 100)
}

// ── Column visibility ──────────────────────────────────────────────────────────
function toggleCol(id) { colVis[id] = !colVis[id]; savePrefs() }
function toggleAllCols(show) { COLUMNS.forEach(c => { colVis[c.id] = show }); savePrefs() }

// ── Column drag reorder ───────────────────────────────────────────────────────
const dragColId = ref(null)
const dropTarget = ref(null)

function onDragStart(e, colId) {
  dragColId.value = colId
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', colId)
}
function onDragOver(e, colId) {
  if (!dragColId.value || dragColId.value === colId) return
  e.preventDefault()
  e.dataTransfer.dropEffect = 'move'
  dropTarget.value = colId
}
function onDrop(e, colId) {
  e.preventDefault()
  if (!dragColId.value || dragColId.value === colId) return
  const order = [...colOrder.value]
  const fromIdx = order.indexOf(dragColId.value)
  const toIdx = order.indexOf(colId)
  if (fromIdx === -1 || toIdx === -1) return
  order.splice(fromIdx, 1)
  order.splice(toIdx, 0, dragColId.value)
  colOrder.value = order
  savePrefs()
  dragColId.value = null
  dropTarget.value = null
}
function onDragEnd() {
  dragColId.value = null
  dropTarget.value = null
}

// ── Formatting ────────────────────────────────────────────────────────────────
const CELL_CLASS = {
  key: 'td-key', project: 'td-project', summary: 'td-summary', points: 'td-num',
  estimated: 'td-time', logged: 'td-time', done_label: 'td-done', labels: 'td-labels',
}
function cellClass(id) { return CELL_CLASS[id] || '' }

function fmtSeconds(s) {
  if (!s) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  if (h === 0) return `${m}m`
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function filteredLabels(labels) {
  if (!Array.isArray(labels)) return []
  const f = props.labelFilter?.toLowerCase()
  if (!f) return labels
  return labels.filter(l => l.toLowerCase().includes(f))
}

// ── Description formatter ─────────────────────────────────────────────────────
function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function formatDesc(text) {
  if (!text?.trim()) return '<em class="desc-empty">（无描述）</em>'
  let s = escHtml(text)
  // {code:lang}...{code} → <pre> block
  s = s.replace(/\{code(?::[^}]*)?\}([\s\S]*?)\{code\}/g,
    (_, body) => `<pre class="desc-code">${body.trim()}</pre>`)
  // {{inline code}} → <code>
  s = s.replace(/\{\{([^}]+)\}\}/g, '<code class="desc-ic">$1</code>')
  // *bold* → <strong>  (Jira wiki bold)
  s = s.replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>')
  // _italic_ → <em>   (Jira wiki italic)
  s = s.replace(/(?<![a-zA-Z0-9])_([^_\n]+)_(?![a-zA-Z0-9])/g, '<em>$1</em>')
  // remaining newlines → <br>
  s = s.replace(/\n/g, '<br>')
  return s
}


function typeCls(t)     { return { 'bg': true, 'bt': t === 'Bug', 'bs': t === 'Story', 'bta': t === 'Task', 'be': t === 'Epic' } }
function statusCls(s)   { return { 'bg': true, 'bst': s === 'To Do' || s === 'Open', 'bre': s === 'Reopened', 'bip': s === 'In Progress', 'bir': s === 'In Review', 'bdo': s === 'Resolved' || s === 'Closed' || s === 'Done', 'bbl': s === 'Blocked' } }
function priorityCls(p) { return { 'bg': true, 'bcr': p === 'Blocker' || p === 'Critical' || p === 'Highest', 'bhi': p === 'High' || p === 'Major', 'bme': p === 'Medium' || p === 'Normal', 'blo': p === 'Minor' || p === 'Low' || p === 'Trivial' || p === 'Lowest' } }

const TYPE_ICONS     = { Bug: '🐛 ', Story: '📖 ', Task: '✅ ', Epic: '⚡ ', 'User Story': '📖 ', 'Sub-task': '🔹 ' }
const STATUS_ICONS   = { Open: '○ ', Reopened: '⟳ ', 'In Progress': '◉ ', 'In Review': '◎ ', Resolved: '✔ ', Closed: '● ', Done: '✔ ', 'To Do': '○ ', Blocked: '⊘ ' }
const PRIORITY_ICONS = { Blocker: '🔴 ', Critical: '🔴 ', Highest: '🔴 ', High: '🟠 ', Major: '🟠 ', Medium: '🔵 ', Normal: '🔵 ', Minor: '⚪ ', Low: '⚪ ', Trivial: '⚪ ', Lowest: '⚪ ' }
function typeIcon(t)     { return TYPE_ICONS[t] ?? '' }
function statusIcon(s)   { return STATUS_ICONS[s] ?? '' }
function priorityIcon(p) { return PRIORITY_ICONS[p] ?? '' }

onMounted(loadPrefs)
</script>

<style scoped>
.ticket-table {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── Stats bar ────────────────────────────────────────────────────────────── */
.stats-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg3);
  border-bottom: 1px solid var(--border);
  font-size: 11.5px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.stat { color: var(--text2); display: flex; align-items: center; gap: 4px; }
.stat b { color: var(--text); font-weight: 600; }
.sep { color: var(--border2); }
.spacer { flex: 1; }
.meta-label { font-size: 11px; color: var(--text3); }
.ago-hint { font-size: 10.5px; color: var(--text3); margin-left: 4px; }

.sdot { width: 6px; height: 6px; border-radius: 50%; background: var(--text3); display: inline-block; }
.sdot-inprog  { background: var(--accent); }
.sdot-review  { background: var(--yellow); }
.sdot-reopen  { background: #db61a2; }
.sdot-done    { background: var(--green); }
.sdot-blocked { background: var(--red); }



.btn {
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text2);
  padding: 4px 9px;
  font-size: 12px;
  cursor: pointer;
  display: flex; align-items: center; gap: 4px;
  white-space: nowrap;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
  user-select: none;
}
.btn:hover  { background: var(--bg4); color: var(--text); }
.btn.active { border-color: var(--accent); color: var(--accent); }
.chev { font-size: 10px; opacity: 0.7; }

.sort-hint { font-size: 11px; color: var(--text3); }
.sort-hint kbd {
  background: var(--bg4); border: 1px solid var(--border2);
  border-radius: 3px; padding: 1px 4px; font-size: 10px; font-family: var(--mono);
}

/* ── Dropdowns ────────────────────────────────────────────────────────────── */
.dropdown { position: relative; }
.col-dd   { margin-left: 2px; }

.dd-menu {
  position: absolute; top: calc(100% + 4px); left: 0;
  background: var(--bg3); border: 1px solid var(--border2);
  border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,.5);
  min-width: 140px; z-index: 200; padding: 3px 0;
  max-height: 260px; overflow-y: auto;
}
.col-menu { left: auto; right: 0; min-width: 160px; }
.col-menu-up { top: auto; bottom: calc(100% + 4px); }

.dd-item {
  padding: 5px 11px; cursor: pointer; display: flex; align-items: center;
  gap: 7px; font-size: 12px; color: var(--text2); transition: background 0.1s;
  user-select: none;
}
.dd-item:hover { background: var(--bg4); color: var(--text); }
.dd-item.sel   { color: var(--accent); }
.chk { width: 14px; font-size: 11px; color: var(--accent); flex-shrink: 0; }

.col-actions {
  display: flex; gap: 0; padding: 4px 0;
  border-bottom: 1px solid var(--border);
}
.col-actions span {
  flex: 1; text-align: center; font-size: 11px; color: var(--text3);
  cursor: pointer; padding: 3px 8px; transition: color 0.12s;
}
.col-actions span:hover { color: var(--accent); }
.col-divider { height: 1px; background: var(--border); margin: 3px 0; }

.col-item {
  padding: 5px 11px; cursor: pointer; display: flex; align-items: center;
  gap: 8px; font-size: 12px; color: var(--text2); transition: background 0.1s;
  user-select: none;
}
.col-item:hover { background: var(--bg4); color: var(--text); }
.tog-box {
  width: 14px; height: 14px; border: 1px solid var(--border2); border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; flex-shrink: 0; transition: background 0.1s;
}
.tog-box.on { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ── Table ────────────────────────────────────────────────────────────────── */
.table-wrap {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border); border-radius: 6px;
  overflow: hidden; background: var(--bg2);
  margin: 0 10px 10px;
}
.table-scroll { overflow-x: auto; }

table { width: 100%; border-collapse: collapse; font-size: 12px; }

thead th {
  background: var(--bg3); color: var(--text2); font-weight: 600;
  font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  padding: 8px 10px; text-align: left; white-space: nowrap;
  border-bottom: 1px solid var(--border); user-select: none;
  cursor: grab;
}
thead th:active { cursor: grabbing; }
thead th.drag-over { box-shadow: inset 2px 0 0 var(--accent); }
thead th.sortable { cursor: pointer; }
thead th.sortable:hover { color: var(--text); background: var(--bg4); }
.th-exp { width: 28px; padding-left: 8px; }

/* ── Chip-filter (Grafana-style multi-select) ─────────────────────────────── */
.chip-filter {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg2);
  font-size: 12px;
  line-height: 1;
  min-height: 26px;
  flex-shrink: 0;
}
.chip-filter.open { border-color: var(--accent); }

.cf-label {
  padding: 4px 6px 4px 8px;
  color: var(--text2);
  font-weight: 500;
  white-space: nowrap;
  border-right: 1px solid var(--border);
  cursor: pointer;
}
.cf-all {
  padding: 4px 6px;
  color: var(--text3);
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
}
.cf-chip {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 2px 2px 2px 6px;
  color: var(--accent);
  white-space: nowrap;
}
.cf-chip-rm, .cf-clear, .cf-toggle {
  background: none; border: none; cursor: pointer;
  color: var(--text3); font-size: 12px; padding: 2px 4px;
  line-height: 1; transition: color 0.1s;
}
.cf-chip-rm:hover, .cf-clear:hover { color: var(--red, #e5534b); }
.cf-toggle { padding: 2px 6px; font-size: 10px; color: var(--text3); }
.cf-toggle:hover { color: var(--text); }
.cf-clear { border-left: 1px solid var(--border); }

.cf-dd {
  position: absolute; top: calc(100% + 4px); left: 0;
  background: var(--bg3); border: 1px solid var(--border2);
  border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,.5);
  min-width: 150px; z-index: 200; padding: 3px 0;
  max-height: 260px; overflow-y: auto;
}
.cf-dd-up { top: auto; bottom: calc(100% + 4px); }
.cf-dd-sep { height: 1px; background: var(--border); margin: 2px 0; }
.cf-dd-item {
  padding: 5px 10px; cursor: pointer; display: flex; align-items: center;
  gap: 7px; font-size: 12px; color: var(--text2); transition: background 0.1s;
  user-select: none; white-space: nowrap;
}
.cf-dd-item:hover { background: var(--bg4); color: var(--text); }
.cf-dd-sel { font-weight: 500; }
.cf-ck {
  width: 15px; height: 15px; border: 1px solid var(--border2); border-radius: 3px;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; flex-shrink: 0; transition: background 0.1s;
}
.cf-ck.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.cf-ck.half { background: var(--accent); border-color: var(--accent); color: #fff; }

/* Search inside dropdown */
.cf-dd-search {
  display: flex; align-items: center; gap: 4px; padding: 4px 8px;
}
.cf-dd-search-icon { font-size: 12px; flex-shrink: 0; opacity: .6; }
.cf-dd-search-input {
  flex: 1; border: none; outline: none; background: transparent;
  color: var(--text); font-size: 12px; padding: 3px 0; min-width: 0;
}
.cf-dd-search-input::placeholder { color: var(--text3); }
.cf-dd-empty { padding: 8px 10px; color: var(--text3); font-size: 12px; text-align: center; }

.sort-ind { display: inline-flex; align-items: center; gap: 1px; margin-left: 4px; color: var(--accent); font-size: 11px; font-weight: 700; }
.sort-ord { font-size: 9px; color: var(--accent2, #2d6fc4); }

tbody tr {
  border-bottom: 1px solid var(--border);
  transition: background 0.1s; cursor: pointer;
}
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: rgba(79,158,255,.04); }
tbody tr.expanded { background: rgba(79,158,255,.06); }
tbody tr.detail-tr { cursor: default; }
tbody tr.detail-tr:hover { background: transparent; }

td { padding: 4px 10px; vertical-align: middle; color: var(--text); white-space: nowrap; }

.td-exp { padding: 4px 4px 4px 8px; width: 28px; }
.exp-arrow {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; font-size: 10px; color: var(--text3);
  transition: transform 0.18s, color 0.12s;
}
.exp-arrow.open { transform: rotate(90deg); color: var(--accent); }

.td-key { white-space: nowrap; }
.td-project { white-space: nowrap; }
.ticket-key {
  font-family: var(--mono); color: var(--accent); font-size: 11.5px;
  font-weight: 600; text-decoration: none;
}
.ticket-key:hover { text-decoration: underline; }

.project-tag {
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text2);
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 6px;
  white-space: nowrap;
}

.td-summary { max-width: 360px; overflow: hidden; text-overflow: ellipsis; }
.summary-text { color: var(--text); }

.td-num { text-align: right; font-family: var(--mono); font-size: 12px; color: var(--text2); }
.pts-val { color: var(--accent); font-weight: 600; }
.td-time { text-align: right; font-family: var(--mono); font-size: 11.5px; color: var(--text2); }
.td-done { font-size: 11px; color: var(--text3); }
.td-labels { max-width: 200px; }

/* ── Label tags ──────────────────────────────────────────────────────────── */
.label-tags { display: flex; flex-wrap: wrap; gap: 3px; }
.label-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
  background: rgba(79,158,255,.1);
  color: var(--accent);
  border: 1px solid rgba(79,158,255,.2);
  white-space: nowrap;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Badges ──────────────────────────────────────────────────────────────── */
.badge {
  display: inline-flex; align-items: center;
  padding: 2px 7px; border-radius: 20px; font-size: 11px;
  font-weight: 500; white-space: nowrap; border: 1px solid transparent;
}
/* type */
.bt  { background: rgba(248,81,73,.13);  color: #f85149; border-color: rgba(248,81,73,.25); }
.bs  { background: rgba(63,185,80,.11);  color: #3fb950; border-color: rgba(63,185,80,.2); }
.bta { background: rgba(79,158,255,.11); color: #4f9eff; border-color: rgba(79,158,255,.22); }
.be  { background: rgba(163,113,247,.11);color: #a371f7; border-color: rgba(163,113,247,.22); }
/* status */
.bst { background: rgba(99,110,123,.18); color: #8b949e; border-color: rgba(99,110,123,.28); }
.bre { background: rgba(219,97,162,.11); color: #db61a2; border-color: rgba(219,97,162,.25); }
.bip { background: rgba(79,158,255,.11); color: #4f9eff; border-color: rgba(79,158,255,.25); }
.bir { background: rgba(210,153,34,.11); color: #d29922; border-color: rgba(210,153,34,.25); }
.bdo { background: rgba(63,185,80,.09);  color: #3fb950; border-color: rgba(63,185,80,.2); }
.bbl { background: rgba(248,81,73,.11);  color: #f85149; border-color: rgba(248,81,73,.25); }
/* priority */
.bcr { background: rgba(248,81,73,.13);  color: #ff7b72; border-color: rgba(248,81,73,.28); }
.bhi { background: rgba(210,153,34,.13); color: #e3b341; border-color: rgba(210,153,34,.28); }
.bme { background: rgba(79,158,255,.11); color: #79c0ff; border-color: rgba(79,158,255,.22); }
.blo { background: rgba(99,110,123,.18); color: #8b949e; border-color: rgba(99,110,123,.28); }

/* ── Assignee ─────────────────────────────────────────────────────────────── */
.assignee-cell { display: flex; align-items: center; gap: 6px; }
.avatar {
  width: 20px; height: 20px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700; flex-shrink: 0; text-transform: uppercase;
}

/* ── Detail panel ─────────────────────────────────────────────────────────── */
.detail-panel {
  background: var(--bg);
  border-top: 1px solid var(--border);
  border-bottom: 2px solid color-mix(in srgb, var(--accent) 35%, transparent);
  animation: detailIn 0.15s ease;
}
.detail-body {
  display: flex;
  gap: 0;
}
@keyframes detailIn {
  from { opacity: 0; transform: translateY(-3px); }
  to   { opacity: 1; transform: translateY(0); }
}
.detail-grid {
  flex: 1;
  padding: 12px 14px 14px 38px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* ── Time Tracking sidebar ──────────────────────────────────────────────────── */
.time-track {
  width: 220px;
  flex-shrink: 0;
  padding: 12px 16px;
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tt-heading {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  color: var(--text3);
  text-transform: uppercase;
  margin-bottom: 2px;
}
.tt-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.tt-label {
  font-size: 10px;
  color: var(--text2);
}
.tt-bar {
  height: 6px;
  border-radius: 3px;
  background: var(--bg3);
  overflow: hidden;
}
.tt-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}
.tt-est { background: #4b9de8; }
.tt-rem { background: #e8974b; }
.tt-log { background: #4bba6e; }
.tt-val {
  font-size: 11px;
  font-family: var(--mono);
  color: var(--text);
}
.di { display: flex; flex-direction: column; gap: 4px; }
.di.full { grid-column: 1 / -1; }
.dl { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); font-weight: 600; }
.dv { font-size: 12.5px; color: var(--text); line-height: 1.5; }
.dv.mono { font-family: var(--mono); font-size: 12px; }
.dv.badge-row { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }

/* Full title row */
.title-row { flex-direction: row; align-items: baseline; gap: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.detail-key { font-family: var(--mono); font-size: 12px; color: var(--accent); font-weight: 600; flex-shrink: 0; text-decoration: none; }
.detail-key:hover { text-decoration: underline; }
.detail-summary { font-size: 14px; font-weight: 600; color: var(--fg); line-height: 1.4; word-break: break-word; }

/* Description */
.desc-text {
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.65;
  word-break: break-word;
  max-height: 220px;
  overflow-y: auto;
}
:deep(.desc-empty) { opacity: 0.45; font-style: italic; }
:deep(.desc-code) {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  padding: 7px 10px;
  font-size: 11.5px;
  font-family: var(--mono);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 6px 0;
  color: var(--text);
  overflow-x: auto;
}
:deep(.desc-ic) {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 5px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--fg);
}

.open-jira-btn {
  display: inline-flex; align-items: center; gap: 4px;
  background: transparent; border: 1px solid var(--border2); border-radius: 4px;
  color: var(--accent); padding: 3px 9px; font-size: 11.5px;
  cursor: pointer; text-decoration: none; transition: background 0.12s, border-color 0.12s;
}
.open-jira-btn:hover { background: rgba(79,158,255,.1); border-color: var(--accent); }

/* ── Footer ───────────────────────────────────────────────────────────────── */
.table-footer {
  padding: 5px 8px; border-top: 1px solid var(--border);
  background: var(--bg3); font-size: 11px; color: var(--text3);
  display: flex; align-items: center; gap: 5px;
  flex-shrink: 0; flex-wrap: wrap;
}
.sort-pills { display: flex; gap: 4px; flex-wrap: wrap; }
.sort-pill {
  background: rgba(79,158,255,.1); border: 1px solid rgba(79,158,255,.22);
  border-radius: 20px; padding: 1px 7px; font-size: 11px; color: var(--accent);
  display: flex; align-items: center; gap: 3px; cursor: default;
}
.pill-x { color: var(--text3); font-size: 10px; margin-left: 3px; cursor: pointer; }
.pill-x:hover { color: var(--red); }
.row-count { color: var(--text3); }

/* ── Empty state ─────────────────────────────────────────────────────────── */
.empty-cell { text-align: center; padding: 36px; color: var(--text3); }

/* ── Scrollbar ────────────────────────────────────────────────────────────── */
::-webkit-scrollbar        { width: 5px; height: 5px; }
::-webkit-scrollbar-track  { background: transparent; }
::-webkit-scrollbar-thumb  { background: var(--border2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text3); }
</style>
