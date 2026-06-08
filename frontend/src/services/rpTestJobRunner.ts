import {
  createRpTestJob,
  deleteRpTestJob,
  getActiveRpTestJob,
  getRpTestJob,
  type ChatCompletionResponse,
  type PromptType,
  type RpTestJob,
  type RpTestJobCreateBody,
  type RpTestJobModelBundle,
  type RpTestJobStepResult,
} from '../api'

export type RpTestJobPhase = 'idle' | 'running' | 'done' | 'error'

export interface RpTestJobSnapshot {
  phase: RpTestJobPhase
  jobId: string | null
  conversationKey: string | null
  status: RpTestJob['status'] | null
  testMode: RpTestJob['test_mode'] | null
  promptType: PromptType | null
  modelBundles: RpTestJobModelBundle[]
  stepResults: RpTestJobStepResult[]
  lastResponse: ChatCompletionResponse | null
  rawContent: string
  reasoningContent: string
  pipelineForcedTailWarning: boolean
  progressStep: number
  progressTotal: number
  savedCount: number
  runGroupId: number | null
  error: string | null
}

export interface RpTestJobStartParams {
  body: RpTestJobCreateBody
  hasForcedTailMerge?: boolean
}

export interface RpTestJobHandlers {
  onComplete?: (job: RpTestJob) => void | Promise<void>
  onError?: (message: string) => void
}

const STORAGE_KEY = 'rpchat:rp-test-job-id'
const POLL_MS = 1000

const initialSnapshot = (): RpTestJobSnapshot => ({
  phase: 'idle',
  jobId: null,
  conversationKey: null,
  status: null,
  testMode: null,
  promptType: null,
  modelBundles: [],
  stepResults: [],
  lastResponse: null,
  rawContent: '',
  reasoningContent: '',
  pipelineForcedTailWarning: false,
  progressStep: 0,
  progressTotal: 0,
  savedCount: 0,
  runGroupId: null,
  error: null,
})

let snapshot: RpTestJobSnapshot = initialSnapshot()
const listeners = new Set<(state: RpTestJobSnapshot) => void>()
let handlers: RpTestJobHandlers = {}
let pollTimer: ReturnType<typeof setInterval> | null = null
let attachedCount = 0

function emit() {
  const copy = { ...snapshot }
  listeners.forEach((listener) => listener(copy))
}

function setSnapshot(partial: Partial<RpTestJobSnapshot>) {
  snapshot = { ...snapshot, ...partial }
  emit()
}

function countProgress(job: RpTestJob): { step: number; total: number } {
  const planSteps = (job.plan?.steps as unknown[] | undefined)?.length ?? 1
  const total = planSteps * job.models.length
  let step = 0
  for (const model of job.models) {
    const ms = job.progress.model_states[model] as { step_index?: number } | undefined
    step += ms?.step_index ?? 0
  }
  return { step, total }
}

function syncFromJob(job: RpTestJob) {
  const bundles = job.progress.model_bundles ?? []
  const firstOk = bundles.find((bundle) => bundle.steps.length > 0)
  const lastStep = firstOk?.steps[firstOk.steps.length - 1]
  const progress = countProgress(job)

  const phase: RpTestJobPhase =
    job.status === 'running'
      ? 'running'
      : job.status === 'done'
        ? 'done'
        : job.status === 'error' || job.status === 'cancelled'
          ? 'error'
          : 'idle'

  setSnapshot({
    phase,
    jobId: job.id,
    conversationKey: job.conversation_key,
    status: job.status,
    testMode: job.test_mode,
    promptType: job.prompt_type,
    modelBundles: bundles,
    stepResults: firstOk?.steps ?? [],
    lastResponse: lastStep?.response ?? null,
    rawContent: lastStep?.rawContent ?? '',
    reasoningContent: lastStep?.reasoningContent ?? '',
    pipelineForcedTailWarning: Boolean(job.has_forced_tail_merge),
    progressStep: progress.step,
    progressTotal: progress.total,
    savedCount: job.progress.saved_count ?? 0,
    runGroupId: job.progress.run_group_id ?? null,
    error: job.error || firstOk?.error || null,
  })
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling(jobId: string) {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    void (async () => {
      if (snapshot.phase !== 'running' || snapshot.jobId !== jobId) {
        stopPolling()
        return
      }
      try {
        const job = await getRpTestJob(jobId)
        syncFromJob(job)
        if (job.status !== 'running') {
          stopPolling()
          if (job.status === 'done') {
            await handlers.onComplete?.(job)
            sessionStorage.removeItem(STORAGE_KEY)
            void deleteRpTestJob(jobId).catch(() => {})
          } else if (job.error) {
            handlers.onError?.(job.error)
            sessionStorage.removeItem(STORAGE_KEY)
          }
        }
      } catch {
        /* ignore transient poll errors */
      }
    })()
  }, POLL_MS)
}

export function getRpTestJobSnapshot(): RpTestJobSnapshot {
  return { ...snapshot }
}

export function subscribeRpTestJob(listener: (state: RpTestJobSnapshot) => void): () => void {
  listeners.add(listener)
  listener({ ...snapshot })
  return () => listeners.delete(listener)
}

export function attachRpTestJobRunner(nextHandlers: RpTestJobHandlers = {}) {
  attachedCount += 1
  handlers = nextHandlers
  return () => {
    attachedCount = Math.max(0, attachedCount - 1)
    if (attachedCount === 0) {
      handlers = {}
    }
  }
}

export async function startRpTestJob(params: RpTestJobStartParams) {
  const job = await createRpTestJob(params.body)
  sessionStorage.setItem(STORAGE_KEY, job.id)
  if (params.hasForcedTailMerge != null) {
    setSnapshot({ pipelineForcedTailWarning: Boolean(params.hasForcedTailMerge) })
  }
  syncFromJob(job)
  startPolling(job.id)
  return job
}

export async function recoverRpTestJob(conversationKey: string) {
  if (snapshot.phase === 'running' && snapshot.conversationKey === conversationKey) {
    return
  }

  let job: RpTestJob | null = null
  const storedId = sessionStorage.getItem(STORAGE_KEY)
  if (storedId) {
    try {
      job = await getRpTestJob(storedId)
    } catch {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }

  if (!job || (job.status !== 'running' && job.conversation_key !== conversationKey)) {
    job = await getActiveRpTestJob(conversationKey)
  }

  if (!job) return

  sessionStorage.setItem(STORAGE_KEY, job.id)
  syncFromJob(job)
  if (job.status === 'running') {
    startPolling(job.id)
  } else if (job.status === 'done') {
    await handlers.onComplete?.(job)
    sessionStorage.removeItem(STORAGE_KEY)
    void deleteRpTestJob(job.id).catch(() => {})
  } else if (job.error) {
    handlers.onError?.(job.error)
  }
}
