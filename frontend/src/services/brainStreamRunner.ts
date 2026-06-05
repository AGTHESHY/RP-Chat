import {
  createStreamSession,
  getActiveStreamSession,
  getStreamSession,
  patchStreamSession,
  saveBrainAnalysis,
  streamChatCompletion,
  type BrainAnalysisDetail,
  type RpEvalDetail,
  type StreamSession,
  type VersionsListResponse,
} from '../api'
import { DEEPSEEK_JSON_OUTPUT_EXTRA } from '../utils/apiProfileStorage'
import { buildBrainUserPayload } from '../utils/brainPayload'
import {
  computeAdaptiveMaxCompletionTokens,
} from '../utils/chatCompletionTimeout'
import { parseBrainJson, type BrainParsed } from '../utils/parseBrainJson'
import type { ResolvedRuntimeRequest } from '../utils/apiProfileStorage'

export type BrainStreamPhase = 'idle' | 'running' | 'done' | 'error'

export interface BrainStreamSnapshot {
  phase: BrainStreamPhase
  sessionId: string | null
  /** RP 历史 history_key，用于严格区分不同测试任务 */
  taskKey: string | null
  evalId: number | null
  raw: string
  reasoning: string
  parsed: BrainParsed | null
  streamPanelActive: boolean
  analyzing: boolean
  viewingBrainRecord: boolean
  savedBrainId: number | null
  error: string | null
}

export interface BrainStreamRunParams {
  taskKey: string
  evalDetail: RpEvalDetail
  requestConfig: ResolvedRuntimeRequest
  brainSystemPrompt: string
  versionCatalog: VersionsListResponse
  evalMode: 'single' | 'multi_compare'
  runGroupId: number
}

export interface BrainStreamHandlers {
  onComplete?: (saved: BrainAnalysisDetail) => void | Promise<void>
  onError?: (message: string) => void
}

const STORAGE_KEY = 'rpchat:brain-stream-session-id'
const REDIS_FLUSH_MS = 400
const POLL_MS = 900

const initialSnapshot = (): BrainStreamSnapshot => ({
  phase: 'idle',
  sessionId: null,
  taskKey: null,
  evalId: null,
  raw: '',
  reasoning: '',
  parsed: null,
  streamPanelActive: false,
  analyzing: false,
  viewingBrainRecord: false,
  savedBrainId: null,
  error: null,
})

let snapshot: BrainStreamSnapshot = initialSnapshot()
const listeners = new Set<(state: BrainStreamSnapshot) => void>()
let handlers: BrainStreamHandlers = {}
let pendingComplete: BrainAnalysisDetail | null = null

let streamAbort: AbortController | null = null
let flushTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let attachedCount = 0
let runToken = 0

function emit() {
  const copy = { ...snapshot }
  listeners.forEach((listener) => listener(copy))
}

function setSnapshot(partial: Partial<BrainStreamSnapshot>) {
  snapshot = { ...snapshot, ...partial }
  emit()
}

function scheduleRedisFlush() {
  if (!snapshot.sessionId || snapshot.phase !== 'running') return
  if (flushTimer) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    void flushToRedis()
  }, REDIS_FLUSH_MS)
}

async function flushToRedis() {
  const { sessionId, raw, reasoning, phase } = snapshot
  if (!sessionId || phase !== 'running') return
  try {
    await patchStreamSession(sessionId, {
      raw_content: raw,
      reasoning_content: reasoning,
      status: 'running',
    })
  } catch {
    /* 暂存失败不阻断流式 */
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function brainTaskRedisKey(taskKey: string, evalId: number): string {
  return `brain:${taskKey}:eval:${evalId}`
}

function syncFromSession(session: StreamSession) {
  const phase: BrainStreamPhase =
    session.status === 'running'
      ? 'running'
      : session.status === 'done'
        ? 'done'
        : session.status === 'error' || session.status === 'cancelled'
          ? 'error'
          : 'idle'
  const evalId =
    typeof session.meta?.eval_id === 'number' ? session.meta.eval_id : snapshot.evalId
  const taskKey =
    typeof session.meta?.history_key === 'string'
      ? session.meta.history_key
      : snapshot.taskKey

  setSnapshot({
    phase,
    sessionId: session.id,
    taskKey,
    evalId,
    raw: session.raw_content || '',
    reasoning: session.reasoning_content || '',
    streamPanelActive: phase === 'running' || (phase === 'done' && !!session.raw_content),
    analyzing: phase === 'running',
    viewingBrainRecord: false,
    error: session.error || null,
    parsed:
      session.parsed_result && typeof session.parsed_result === 'object'
        ? (session.parsed_result as unknown as BrainParsed)
        : snapshot.parsed,
  })
}

function startPolling(sessionId: string) {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    void (async () => {
      if (snapshot.phase !== 'running' || snapshot.sessionId !== sessionId) {
        stopPolling()
        return
      }
      if (streamAbort) return
      try {
        const session = await getStreamSession(sessionId)
        if (session.status !== 'running') {
          stopPolling()
          syncFromSession(session)
          if (session.status === 'error' && session.error) {
            handlers.onError?.(session.error)
          }
        } else if (session.raw_content.length > snapshot.raw.length) {
          setSnapshot({
            raw: session.raw_content,
            reasoning: session.reasoning_content || snapshot.reasoning,
          })
        }
      } catch {
        /* ignore poll errors */
      }
    })()
  }, POLL_MS)
}

async function recoverSession() {
  const storedId = sessionStorage.getItem(STORAGE_KEY)
  if (storedId && snapshot.phase === 'running' && snapshot.sessionId === storedId) {
    return
  }

  let session: StreamSession | null = null
  if (storedId) {
    try {
      session = await getStreamSession(storedId)
    } catch {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }

  if (!session && snapshot.taskKey != null && snapshot.evalId != null) {
    session = await getActiveStreamSession(
      'brain',
      brainTaskRedisKey(snapshot.taskKey, snapshot.evalId),
    )
  }

  if (!session) return

  sessionStorage.setItem(STORAGE_KEY, session.id)
  syncFromSession(session)
  if (session.status === 'running' && !streamAbort) {
    startPolling(session.id)
  }
}

function flushPendingComplete() {
  if (!pendingComplete || !handlers.onComplete) return
  const saved = pendingComplete
  pendingComplete = null
  void handlers.onComplete(saved)
}

export function getBrainStreamSnapshot(): BrainStreamSnapshot {
  return { ...snapshot }
}

export function subscribeBrainStream(listener: (state: BrainStreamSnapshot) => void) {
  listeners.add(listener)
  listener({ ...snapshot })
  return () => listeners.delete(listener)
}

export function setBrainStreamHandlers(next: BrainStreamHandlers) {
  handlers = next
  flushPendingComplete()
}

export function attachBrainStream() {
  attachedCount += 1
  void recoverSession()
}

export function detachBrainStream() {
  attachedCount = Math.max(0, attachedCount - 1)
}

export function abortBrainStream() {
  streamAbort?.abort()
}

export function brainStreamActiveForTask(taskKey: string | null, evalId: number | null = null): boolean {
  if (!taskKey || snapshot.taskKey !== taskKey) return false
  if (evalId != null && snapshot.evalId !== evalId) return false
  return snapshot.phase === 'running' || snapshot.analyzing
}

/** @deprecated 使用 brainStreamActiveForTask */
export function brainStreamActiveForEval(evalId: number | null): boolean {
  return brainStreamActiveForTask(snapshot.taskKey, evalId)
}

export async function runBrainStream(params: BrainStreamRunParams): Promise<void> {
  if (snapshot.phase === 'running') {
    abortBrainStream()
  }

  const token = ++runToken
  const { taskKey, evalDetail, requestConfig, brainSystemPrompt, versionCatalog, evalMode, runGroupId } =
    params
  const evaluatedModelCount = Math.max(
    1,
    evalDetail.evaluated_models?.length ?? (evalMode === 'multi_compare' ? 2 : 1),
  )

  let sessionId: string
  try {
    const session = await createStreamSession({
      scope: 'brain',
      task_key: brainTaskRedisKey(taskKey, evalDetail.id),
      meta: {
        eval_id: evalDetail.id,
        eval_mode: evalMode,
        history_key: taskKey,
        run_group_id: runGroupId,
        user_id: evalDetail.user_id,
        role_id: evalDetail.role_id,
        app_name: evalDetail.app_name,
        role_name: evalDetail.role_name,
      },
    })
    sessionId = session.id
    sessionStorage.setItem(STORAGE_KEY, sessionId)
  } catch (error) {
    handlers.onError?.(error instanceof Error ? error.message : '创建流式会话失败')
    return
  }

  setSnapshot({
    phase: 'running',
    sessionId,
    taskKey,
    evalId: evalDetail.id,
    raw: '',
    reasoning: '',
    parsed: null,
    streamPanelActive: true,
    analyzing: true,
    viewingBrainRecord: false,
    savedBrainId: null,
    error: null,
  })

  streamAbort = new AbortController()
  const abortSignal = streamAbort.signal

  try {
    const userContent = await buildBrainUserPayload({ evalDetail, versionCatalog })
    const extra = {
      ...(requestConfig.extra_body ?? {}),
      ...DEEPSEEK_JSON_OUTPUT_EXTRA,
    }

    const resp = await streamChatCompletion(
      {
        base_url: requestConfig.base_url,
        api_key: requestConfig.api_key,
        model: requestConfig.model,
        temperature: requestConfig.temperature,
        top_k: requestConfig.top_k ?? null,
        extra_body: extra,
        system_prompt: brainSystemPrompt,
        user_content: userContent,
        max_completion_tokens: computeAdaptiveMaxCompletionTokens(evaluatedModelCount),
      },
      {
        onContent: (_piece, full) => {
          if (token !== runToken) return
          setSnapshot({ raw: full })
          scheduleRedisFlush()
        },
        onReasoning: (_piece, full) => {
          if (token !== runToken) return
          setSnapshot({ reasoning: full })
          scheduleRedisFlush()
        },
      },
      abortSignal,
    )

    if (token !== runToken) return

    const raw = resp.raw_content || resp.error || ''
    setSnapshot({ raw })

    if (resp.status !== 200) {
      const errDetail = (resp.error || '').trim().slice(0, 240)
      const message = errDetail
        ? `智脑请求失败: HTTP ${resp.status} — ${errDetail}`
        : `智脑请求失败: HTTP ${resp.status}`
      await patchStreamSession(sessionId, {
        status: 'error',
        raw_content: raw,
        reasoning_content: snapshot.reasoning,
        error: message,
      }).catch(() => {})
      setSnapshot({
        phase: 'error',
        analyzing: false,
        streamPanelActive: false,
        error: message,
      })
      handlers.onError?.(message)
      sessionStorage.removeItem(STORAGE_KEY)
      return
    }

    const parsed = parseBrainJson(raw)
    if (!parsed.ok || !parsed.data) {
      const message = parsed.error || '智脑 JSON 解析失败'
      await patchStreamSession(sessionId, {
        status: 'error',
        raw_content: raw,
        reasoning_content: snapshot.reasoning,
        error: message,
      }).catch(() => {})
      setSnapshot({
        phase: 'error',
        analyzing: false,
        streamPanelActive: false,
        error: message,
      })
      handlers.onError?.(message)
      sessionStorage.removeItem(STORAGE_KEY)
      return
    }

    setSnapshot({ parsed: parsed.data, viewingBrainRecord: false })

    const saved = await saveBrainAnalysis({
      rp_eval_id: evalDetail.id,
      user_id: evalDetail.user_id,
      role_id: evalDetail.role_id,
      app_name: evalDetail.app_name,
      role_name: evalDetail.role_name,
      round_start: evalDetail.round_start,
      round_end: evalDetail.round_end,
      compress_prompt_version: evalDetail.compress_prompt_version,
      merge_prompt_version: evalDetail.merge_prompt_version,
      brain_system_prompt: brainSystemPrompt,
      brain_result: JSON.parse(JSON.stringify(parsed.data)) as Record<string, unknown>,
      raw_model_output: raw,
      model: requestConfig.model,
      top_k: requestConfig.top_k ?? null,
      temperature: requestConfig.temperature,
      eval_mode: evalMode,
      evaluated_models: evalDetail.evaluated_models ?? [],
      run_group_id: runGroupId,
    })

    await patchStreamSession(sessionId, {
      status: 'done',
      raw_content: raw,
      reasoning_content: snapshot.reasoning,
      parsed_result: parsed.data as unknown as Record<string, unknown>,
    }).catch(() => {})

    setSnapshot({
      phase: 'done',
      analyzing: false,
      streamPanelActive: true,
      savedBrainId: saved.id,
    })
    sessionStorage.removeItem(STORAGE_KEY)

    if (handlers.onComplete) {
      void handlers.onComplete(saved)
    } else {
      pendingComplete = saved
    }
  } catch (error) {
    if (token !== runToken) return
    if (error instanceof DOMException && error.name === 'AbortError') {
      const message = '智脑分析已取消'
      await patchStreamSession(sessionId, {
        status: 'cancelled',
        raw_content: snapshot.raw,
        reasoning_content: snapshot.reasoning,
        error: message,
      }).catch(() => {})
      setSnapshot({
        phase: 'error',
        analyzing: false,
        streamPanelActive: false,
        error: message,
      })
      handlers.onError?.(message)
      sessionStorage.removeItem(STORAGE_KEY)
      return
    }
    const message = error instanceof Error ? error.message : '智脑分析失败'
    await patchStreamSession(sessionId, {
      status: 'error',
      raw_content: snapshot.raw,
      reasoning_content: snapshot.reasoning,
      error: message,
    }).catch(() => {})
    setSnapshot({
      phase: 'error',
      analyzing: false,
      streamPanelActive: false,
      error: message,
    })
    handlers.onError?.(message)
    sessionStorage.removeItem(STORAGE_KEY)
  } finally {
    if (token === runToken) {
      streamAbort = null
      stopPolling()
      if (flushTimer) {
        clearTimeout(flushTimer)
        flushTimer = null
      }
    }
  }
}

export async function recoverBrainStreamForTask(taskKey: string, evalId: number) {
  if (
    snapshot.phase === 'running' &&
    snapshot.taskKey === taskKey &&
    snapshot.evalId === evalId
  ) {
    return
  }
  const session = await getActiveStreamSession('brain', brainTaskRedisKey(taskKey, evalId))
  if (!session) return
  sessionStorage.setItem(STORAGE_KEY, session.id)
  syncFromSession(session)
  if (session.status === 'running' && !streamAbort) {
    startPolling(session.id)
  }
}

/** @deprecated 使用 recoverBrainStreamForTask */
export async function recoverBrainStreamForEval(evalId: number) {
  if (!snapshot.taskKey) return
  await recoverBrainStreamForTask(snapshot.taskKey, evalId)
}
