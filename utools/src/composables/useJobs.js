import { reactive, ref } from 'vue'

/**
 * Manages a list of concurrent tool jobs.
 * @param {string} cmd - CLI command name (e.g. 'bisync')
 */
export function useJobs(cmd) {
  // reactive array so nested job property mutations (lines.push, status =) are tracked
  const jobs = reactive([])
  const selectedId = ref(null)

  function addJob(label, args) {
    const id = crypto.randomUUID()
    const job = reactive({
      id,
      label,
      args,
      status: 'running',
      lines: [],
      startedAt: new Date(),
      exitCode: null,
    })

    jobs.unshift(job)
    selectedId.value = id

    window.myscriptAPI.runTool(
      id,
      cmd,
      args,
      (line) => job.lines.push(line),
      (code) => {
        job.exitCode = code
        job.status = code === -1 ? 'stopped' : code === 0 ? 'done' : 'error'
      },
    )

    return job
  }

  function stopJob(id) {
    window.myscriptAPI.stopTool(id)
  }

  function removeJob(id) {
    const idx = jobs.findIndex(j => j.id === id)
    if (idx !== -1) {
      if (jobs[idx].status === 'running') stopJob(id)
      if (selectedId.value === id) {
        selectedId.value = jobs[idx + 1]?.id ?? jobs[idx - 1]?.id ?? null
      }
      jobs.splice(idx, 1)
    }
  }

  function selectJob(id) {
    selectedId.value = id
  }

  const selectedJob = () => jobs.find(j => j.id === selectedId.value) ?? null

  return { jobs, selectedId, selectedJob, addJob, stopJob, removeJob, selectJob }
}
