import { buildQuery } from './query'
import { CHAT_TIMEOUT_BASE_SECONDS } from '../utils/chatCompletionTimeout'

export type BaselineVersion = 'v1' | 'v2'
export type PromptVersion = BaselineVersion | string
export type PromptType = 'segment_compress' | 'history_merge'
export type PromptLang = 'zh' | 'en'

export interface VersionInfo {
  version: string
  base_version: string
  status: string
  created_at?: string | null
}

export interface VersionsListResponse {
  baselines: string[]
  custom: VersionInfo[]
  drafts: VersionInfo[]
}

export interface VersionMetaResponse {
  version: string
  base_version: string
  is_baseline: boolean
  status: string
  is_draft: boolean
  has_en?: boolean
}

export interface PromptContentResponse {
  version?: string
  prompt_type?: string
  lang?: string
  content_sfw: string
  content_nsfw: string
  content: string
  readonly?: boolean
}

export interface DocResponse {
  version: string
  filename: string
  content: string
  readonly?: boolean
}

export interface DraftUpdatePayload {
  prompt_type?: string
  lang?: string
  content_sfw?: string
  content_nsfw?: string
  doc_content?: string
}

export interface PromptTestResultSummary {
  id: number
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  run_group_id: number
  prompt_type: PromptType
  round_start: number
  round_end: number
  prompt_version: string
  model: string
  top_k: number | null
  temperature: number
  created_at: string | null
  updated_at: string | null
}

export interface PromptTestResultDetail extends PromptTestResultSummary {
  expected_result: Record<string, unknown>
}

export function listPromptTestResults(params?: {
  user_id?: string
  role_id?: string
  role_name?: string
  prompt_type?: string
  run_group_id?: number
}) {
  return request<PromptTestResultSummary[]>(
    `/api/prompt-test-results${buildQuery(params ?? {})}`,
  )
}

export function getPromptTestResult(id: number) {
  return request<PromptTestResultDetail>(`/api/prompt-test-results/${id}`)
}

export function getPromptTestResultByConversation(params: {
  user_id: string
  role_id: string
  app_name: string
  prompt_type: PromptType
  model?: string
  run_group_id?: number
}) {
  const search = new URLSearchParams()
  search.set('user_id', params.user_id)
  search.set('role_id', params.role_id)
  search.set('app_name', params.app_name)
  search.set('prompt_type', params.prompt_type)
  if (params.model) search.set('model', params.model)
  if (params.run_group_id != null) search.set('run_group_id', String(params.run_group_id))
  return request<PromptTestResultDetail>(
    `/api/prompt-test-results/by-conversation?${search.toString()}`,
  )
}

export function savePromptTestResult(body: {
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  prompt_type: PromptType
  expected_result: Record<string, unknown>
  round_start: number
  round_end: number
  prompt_version: string
  model: string
  top_k: number | null
  temperature: number
  /** 重跑：归属到该请求，按 model+prompt_type upsert */
  run_group_id?: number
}) {
  return request<PromptTestResultDetail>('/api/prompt-test-results', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export interface RpHistorySummary {
  conversation_key: string
  /** 唯一标识一次测试请求 */
  history_key: string
  run_group_id: number
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  prompt_version: string
  has_compress: boolean
  has_merge: boolean
  model_count: number
  round_start: number
  round_end: number
  latest_updated_at: string | null
}

export interface RpHistoryModelRun {
  model: string
  compress_record_id: number | null
  merge_record_id: number | null
  compress: Record<string, unknown> | null
  merge: Record<string, unknown> | null
  compress_run: RpHistoryRunMeta | null
  merge_run: RpHistoryRunMeta | null
  latest_updated_at: string | null
}

export interface RpHistoryRunMeta {
  prompt_version: string
  model: string
  top_k: number | null
  temperature: number
  updated_at: string | null
}

export interface RpHistoryDetail {
  conversation_key: string
  history_key: string
  run_group_id: number
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  prompt_version: string
  round_start: number
  round_end: number
  model_runs: RpHistoryModelRun[]
  /** 未指定 model 时取最近更新的模型 run */
  compress: Record<string, unknown> | null
  merge: Record<string, unknown> | null
  compress_record_id: number | null
  merge_record_id: number | null
  compress_updated_at: string | null
  merge_updated_at: string | null
  compress_run: RpHistoryRunMeta | null
  merge_run: RpHistoryRunMeta | null
}

export function listRpHistory(params?: {
  user_id?: string
  role_id?: string
  role_name?: string
}) {
  return request<RpHistorySummary[]>(`/api/rp-history${buildQuery(params ?? {})}`)
}

export function getRpHistoryDetail(params: {
  user_id: string
  role_id: string
  app_name: string
  run_group_id?: number
  model?: string
}) {
  const search = new URLSearchParams()
  search.set('user_id', params.user_id)
  search.set('role_id', params.role_id)
  search.set('app_name', params.app_name)
  if (params.run_group_id != null) {
    search.set('run_group_id', String(params.run_group_id))
  }
  if (params.model) {
    search.set('model', params.model)
  }
  return request<RpHistoryDetail>(`/api/rp-history/detail?${search.toString()}`)
}

export function deleteRpHistory(params: {
  user_id: string
  role_id: string
  app_name: string
  run_group_id: number
}) {
  const search = new URLSearchParams()
  search.set('user_id', params.user_id)
  search.set('role_id', params.role_id)
  search.set('app_name', params.app_name)
  search.set('run_group_id', String(params.run_group_id))
  return request<{
    ok: boolean
    run_group_id: number
    deleted_ids: number[]
    deleted_count: number
  }>(`/api/rp-history?${search.toString()}`, { method: 'DELETE' })
}

export function deleteRpHistoryModels(body: {
  user_id: string
  role_id: string
  app_name: string
  run_group_id: number
  models: string[]
}) {
  return request<{
    ok: boolean
    run_group_id: number
    models: string[]
    deleted_ids: number[]
    deleted_count: number
  }>('/api/rp-history/delete-models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export interface ChatCompletionRequest {
  base_url: string
  api_key: string
  model: string
  temperature: number
  top_k: number | null
  system_prompt: string
  user_content: string
  /** 上游 LLM 请求超时（秒），未传时后端默认 120 */
  timeout_seconds?: number
  /** 生成 token 上限，未传时后端默认 4096 */
  max_completion_tokens?: number
  /** 与 API 配置页「额外请求体参数」合并进上游请求 */
  extra_body?: Record<string, unknown>
}

export interface ChatCompletionResponse {
  status: number
  raw_content?: string
  reasoning_content?: string
  usage?: Record<string, number>
  finish_reason?: string
  error?: string
  raw_text?: string
}

export interface TranslateRequest {
  base_url: string
  api_key: string
  model: string
  temperature: number
}

export interface BrainRevisionPlanItemPayload {
  section: string
  action: string
  summary: string
  detail: string
}

export interface BrainRevisionPlanPayload {
  sfw: BrainRevisionPlanItemPayload[]
  nsfw: BrainRevisionPlanItemPayload[]
}

export interface BrainRevisionRequest extends TranslateRequest {
  prompt_type: 'segment_compress' | 'history_merge'
  focus_areas: string[]
  linked_issues: string[]
  rationale: string
  revision_plan: BrainRevisionPlanPayload
}

export interface BrainRevisionBatchModulePayload {
  prompt_type: 'segment_compress' | 'history_merge'
  focus_areas: string[]
  linked_issues: string[]
  rationale: string
  revision_plan: BrainRevisionPlanPayload
}

export interface BrainRevisionBatchRequest extends TranslateRequest {
  modules: BrainRevisionBatchModulePayload[]
}

export const NSFW_MARKER = '{{NSFW}}'
export const NSFW_PART_SEP = '\n---NSFW_PART---\n'

export function composePrompt(
  contentSfw: string,
  contentNsfw: string,
  includeNsfw: boolean,
): string {
  const collapseBlankLines = (text: string) => text.replace(/\n{3,}/g, '\n\n').trim()

  if (!includeNsfw || !contentNsfw.trim()) {
    return collapseBlankLines(contentSfw.replace(/\n*{{NSFW}}\n*/g, '\n'))
  }

  let result = contentSfw
  for (const part of contentNsfw.split(NSFW_PART_SEP)) {
    const trimmed = part.trim()
    if (!trimmed) continue
    result = result.replace(NSFW_MARKER, trimmed)
  }
  return collapseBlankLines(result.replace(/\n*{{NSFW}}\n*/g, '\n'))
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init)
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `Request failed: ${resp.status}`)
  }
  return resp.json() as Promise<T>
}

export function listVersions() {
  return request<VersionsListResponse>('/api/versions')
}

export function createVersion(version: string, baseVersion?: string | null) {
  return request<VersionMetaResponse>('/api/versions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      version,
      base_version: baseVersion || null,
    }),
  })
}

export function getVersionMeta(version: string) {
  return request<VersionMetaResponse>(`/api/versions/${encodeURIComponent(version)}`)
}

export function getVersionPrompt(
  version: string,
  promptType: PromptType,
  lang: PromptLang,
  includeNsfw = true,
) {
  const params = includeNsfw ? '' : '?include_nsfw=false'
  return request<PromptContentResponse>(
    `/api/versions/${encodeURIComponent(version)}/prompts/${promptType}/${lang}${params}`,
  )
}

export function getVersionDoc(version: string) {
  return request<DocResponse>(`/api/versions/${encodeURIComponent(version)}/docs`)
}

export function saveDraft(version: string, payload: DraftUpdatePayload) {
  return request<{ ok: boolean; version: string; updated_at: string }>(
    `/api/versions/${encodeURIComponent(version)}/draft`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export function commitVersion(version: string) {
  return request<{ ok: boolean; version: string; status: string }>(
    `/api/versions/${encodeURIComponent(version)}/commit`,
    { method: 'POST' },
  )
}

export function translateVersion(version: string, body: TranslateRequest) {
  return request<{ ok: boolean; version: string; translated: string[] }>(
    `/api/versions/${encodeURIComponent(version)}/translate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export function applyBrainRevision(version: string, body: BrainRevisionRequest) {
  return request<{
    ok: boolean
    version: string
    prompt_type: string
    revised: string[]
    changed?: boolean
    changed_fields?: string[]
  }>(
    `/api/versions/${encodeURIComponent(version)}/brain-revision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
}

export function applyBrainRevisionBatch(version: string, body: BrainRevisionBatchRequest) {
  return request<{
    ok: boolean
    version: string
    modules: Array<{
      ok: boolean
      version: string
      prompt_type: string
      revised: string[]
      changed?: boolean
      changed_fields?: string[]
    }>
    changed_fields: string[]
  }>(`/api/versions/${encodeURIComponent(version)}/brain-revision-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function discardDraft(version: string) {
  return request<{ ok: boolean; version: string }>(
    `/api/versions/${encodeURIComponent(version)}/draft`,
    { method: 'DELETE' },
  )
}

export function deleteVersion(version: string) {
  return request<{ ok: boolean; deleted: string[] }>(
    `/api/versions/${encodeURIComponent(version)}`,
    { method: 'DELETE' },
  )
}

export function runChatCompletion(body: ChatCompletionRequest) {
  return request<ChatCompletionResponse>('/api/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export interface ChatStreamResult {
  status: number
  raw_content: string
  reasoning_content: string
  finish_reason?: string | null
  usage?: Record<string, number>
  error?: string
}

export interface ChatStreamCallbacks {
  onContent?: (piece: string, full: string) => void
  onReasoning?: (piece: string, full: string) => void
  onDone?: (result: ChatStreamResult) => void
  onError?: (message: string) => void
}

export async function streamChatCompletion(
  body: ChatCompletionRequest,
  callbacks: ChatStreamCallbacks = {},
  signal?: AbortSignal,
): Promise<ChatStreamResult> {
  const idleTimeoutSec = body.timeout_seconds ?? CHAT_TIMEOUT_BASE_SECONDS
  const idleAbort = new AbortController()
  let idleTimer: ReturnType<typeof setTimeout> | null = null
  let finished = false

  const stopIdleTimer = () => {
    finished = true
    if (idleTimer !== null) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
  }

  /** 有数据流动时重置；流式进行中不设总时长上限 */
  const bumpIdleTimer = () => {
    if (finished) return
    if (idleTimer !== null) clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      if (!finished) idleAbort.abort()
    }, idleTimeoutSec * 1000)
  }

  const onExternalAbort = () => idleAbort.abort()
  if (signal) {
    if (signal.aborted) idleAbort.abort()
    else signal.addEventListener('abort', onExternalAbort, { once: true })
  }

  bumpIdleTimer()

  let result: ChatStreamResult = {
    status: 200,
    raw_content: '',
    reasoning_content: '',
    finish_reason: null,
  }

  try {
    const resp = await fetch('/api/chat/completions/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: idleAbort.signal,
    })

    result = {
      status: resp.status,
      raw_content: '',
      reasoning_content: '',
      finish_reason: null,
    }

    if (!resp.ok || !resp.body) {
      stopIdleTimer()
      const text = await resp.text().catch(() => '')
      result.error = text || `Request failed: ${resp.status}`
      callbacks.onError?.(result.error)
      return result
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    const handleEvent = (dataStr: string) => {
      if (!dataStr) return
      let evt: Record<string, unknown>
      try {
        evt = JSON.parse(dataStr)
      } catch {
        bumpIdleTimer()
        return
      }
      const type = evt.type
      if (type === 'delta') {
        bumpIdleTimer()
        const content = typeof evt.content === 'string' ? evt.content : ''
        const reasoning = typeof evt.reasoning === 'string' ? evt.reasoning : ''
        if (content) {
          result.raw_content += content
          callbacks.onContent?.(content, result.raw_content)
        }
        if (reasoning) {
          result.reasoning_content += reasoning
          callbacks.onReasoning?.(reasoning, result.reasoning_content)
        }
      } else if (type === 'done') {
        stopIdleTimer()
        result.finish_reason = (evt.finish_reason as string | null) ?? null
        if (evt.usage && typeof evt.usage === 'object') {
          result.usage = evt.usage as Record<string, number>
        }
      } else if (type === 'error') {
        stopIdleTimer()
        result.status = typeof evt.status === 'number' ? evt.status : 500
        result.error = typeof evt.error === 'string' ? evt.error : '流式请求失败'
        callbacks.onError?.(result.error)
      } else {
        bumpIdleTimer()
      }
    }

    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      bumpIdleTimer()
      buffer += decoder.decode(value, { stream: true })
      let sepIndex: number
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex)
        buffer = buffer.slice(sepIndex + 2)
        for (const line of rawEvent.split('\n')) {
          const trimmed = line.trim()
          if (trimmed.startsWith('data:')) {
            handleEvent(trimmed.slice('data:'.length).trim())
          }
        }
      }
    }
    stopIdleTimer()
    const tail = buffer.trim()
    if (tail.startsWith('data:')) {
      handleEvent(tail.slice('data:'.length).trim())
    }

    callbacks.onDone?.(result)
    return result
  } catch (error) {
    stopIdleTimer()
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (signal?.aborted) throw error
      result.status = 504
      result.error = `连续 ${idleTimeoutSec}s 无数据，连接已断开`
      callbacks.onError?.(result.error)
      return result
    }
    throw error
  } finally {
    if (signal) signal.removeEventListener('abort', onExternalAbort)
  }
}

export type JailbreakContentMode = 'plain' | 'variable'
export type JailbreakVariableGroup = 'nsfw' | 'general' | 'custom'

export interface JailbreakVariableModule {
  id: string
  key: string
  label: string
  body: string
  enabled: boolean
  group: JailbreakVariableGroup
  order: number
}

export interface JailbreakBaseSection {
  id: string
  name: string
  content: string
  alwaysOn: boolean
  order: number
}

export interface JailbreakModulesDoc {
  baseSections: JailbreakBaseSection[]
  variables: JailbreakVariableModule[]
}

export interface JailbreakRecord {
  id: number
  scheme_name: string
  version: string
  target_model: string
  content: string
  content_mode: JailbreakContentMode
  modules_json: JailbreakModulesDoc | null
  changelog: string
  created_at: string | null
  updated_at: string | null
}

export interface JailbreakSchemeSummary {
  scheme_name: string
  version_count: number
  latest_version: string
  latest_id: number
  target_model: string
  updated_at: string | null
}

export interface JailbreakCreatePayload {
  scheme_name: string
  target_model: string
  content: string
  changelog?: string
  version?: string
  content_mode?: JailbreakContentMode
  modules_json?: JailbreakModulesDoc | null
}

export interface JailbreakUpdatePayload {
  target_model?: string
  content?: string
  changelog?: string
  content_mode?: JailbreakContentMode
  modules_json?: JailbreakModulesDoc | null
}

export function listJailbreaks(params?: { scheme_name?: string; target_model?: string }) {
  return request<JailbreakRecord[]>(`/api/jailbreaks${buildQuery(params ?? {})}`)
}

export function listJailbreakSchemes() {
  return request<JailbreakSchemeSummary[]>('/api/jailbreaks/schemes')
}

export function getJailbreak(id: number) {
  return request<JailbreakRecord>(`/api/jailbreaks/${id}`)
}

export function createJailbreak(payload: JailbreakCreatePayload) {
  return request<JailbreakRecord>('/api/jailbreaks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateJailbreak(id: number, payload: JailbreakUpdatePayload) {
  return request<JailbreakRecord>(`/api/jailbreaks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteJailbreak(id: number) {
  return request<{ ok: boolean; deleted: JailbreakRecord }>(`/api/jailbreaks/${id}`, {
    method: 'DELETE',
  })
}

export function forkJailbreakNextVersion(id: number) {
  return request<JailbreakRecord>(`/api/jailbreaks/${id}/next-version`, {
    method: 'POST',
  })
}

export interface ChatQaCase {
  id: number
  user_id: string
  role_id: string
  role_name: string
  app_name: string
  question: string
  answer: string
  status: string
  u_time: number
  created_at: string | null
  updated_at: string | null
}

export interface ChatQaConversationSummary {
  conversation_key: string
  user_id: string
  role_id: string
  role_name: string
  app_name: string
  message_count: number
  latest_u_time: number
}

export interface ChatQaConversationDetail {
  conversation_key: string
  user_id: string
  role_id: string
  role_name: string
  app_name: string
  message_count: number
  messages: ChatQaCase[]
}

export function listChatQaCases(params?: {
  user_id?: string
  role_id?: string
  role_name?: string
}) {
  return request<ChatQaCase[]>(`/api/chat-qa-cases${buildQuery(params ?? {})}`)
}

export function listChatQaConversations(params?: {
  user_id?: string
  role_id?: string
  role_name?: string
}) {
  return request<ChatQaConversationSummary[]>(
    `/api/chat-qa-conversations${buildQuery(params ?? {})}`,
  )
}

export function getChatQaConversation(params: {
  user_id: string
  role_id: string
  app_name: string
}) {
  const search = new URLSearchParams()
  search.set('user_id', params.user_id)
  search.set('role_id', params.role_id)
  search.set('app_name', params.app_name)
  return request<ChatQaConversationDetail>(
    `/api/chat-qa-conversations/messages?${search.toString()}`,
  )
}

export function getChatQaCase(id: number) {
  return request<ChatQaCase>(`/api/chat-qa-cases/${id}`)
}

export interface RpEvalSummary {
  id: number
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  round_start: number
  round_end: number
  has_compress: boolean
  has_merge: boolean
  compress_prompt_version: string
  merge_prompt_version: string
  model: string
  eval_mode: 'single' | 'multi_compare'
  evaluated_models: string[]
  run_group_id?: number
  overall_score: number
  overall_confidence: number
  created_at: string | null
}

export interface RpEvalDetail extends RpEvalSummary {
  eval_system_prompt: string
  eval_result: Record<string, unknown>
  raw_model_output: string
  top_k: number | null
  temperature: number
}

export interface RpEvalSavePayload {
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  round_start: number
  round_end: number
  has_compress: boolean
  has_merge: boolean
  compress_prompt_version?: string
  merge_prompt_version?: string
  eval_system_prompt: string
  eval_result: Record<string, unknown>
  raw_model_output: string
  model: string
  top_k: number | null
  temperature: number
  eval_mode?: 'single' | 'multi_compare'
  evaluated_models?: string[]
  run_group_id?: number
}

export function listRpEvaluations(params: {
  user_id: string
  role_id: string
  app_name: string
  run_group_id?: number
}) {
  const search = new URLSearchParams()
  search.set('user_id', params.user_id)
  search.set('role_id', params.role_id)
  search.set('app_name', params.app_name)
  if (params.run_group_id != null) {
    search.set('run_group_id', String(params.run_group_id))
  }
  return request<RpEvalSummary[]>(`/api/rp-evaluations?${search.toString()}`)
}

export function getRpEval(id: number) {
  return request<RpEvalDetail>(`/api/rp-evaluations/${id}`)
}

export function saveRpEval(body: RpEvalSavePayload) {
  return request<RpEvalDetail>('/api/rp-evaluations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteRpEval(id: number) {
  return request<{ ok: boolean; deleted: RpEvalDetail }>(`/api/rp-evaluations/${id}`, {
    method: 'DELETE',
  })
}

export type BrainRecommendation = 'minor' | 'major' | 'hold'

export interface BrainAnalysisSummary {
  id: number
  rp_eval_id: number
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  round_start: number
  round_end: number
  compress_prompt_version: string
  merge_prompt_version: string
  overall: BrainRecommendation
  model: string
  eval_mode?: 'single' | 'multi_compare'
  evaluated_models?: string[]
  run_group_id?: number
  created_at: string | null
}

export interface BrainAnalysisDetail extends BrainAnalysisSummary {
  brain_system_prompt: string
  brain_result: Record<string, unknown>
  raw_model_output: string
  top_k: number | null
  temperature: number
}

export interface BrainSavePayload {
  rp_eval_id: number
  user_id: string
  role_id: string
  app_name: string
  role_name: string
  round_start: number
  round_end: number
  compress_prompt_version?: string
  merge_prompt_version?: string
  brain_system_prompt: string
  brain_result: Record<string, unknown>
  raw_model_output: string
  model: string
  top_k: number | null
  temperature: number
  eval_mode?: 'single' | 'multi_compare'
  evaluated_models?: string[]
  run_group_id?: number
}

export function listBrainAnalyses(params: {
  user_id: string
  role_id: string
  app_name: string
  run_group_id?: number
}) {
  const search = new URLSearchParams()
  search.set('user_id', params.user_id)
  search.set('role_id', params.role_id)
  search.set('app_name', params.app_name)
  if (params.run_group_id != null) {
    search.set('run_group_id', String(params.run_group_id))
  }
  return request<BrainAnalysisSummary[]>(`/api/brain-analyses?${search.toString()}`)
}

export function getBrainAnalysis(id: number) {
  return request<BrainAnalysisDetail>(`/api/brain-analyses/${id}`)
}

export function saveBrainAnalysis(body: BrainSavePayload) {
  return request<BrainAnalysisDetail>('/api/brain-analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteBrainAnalysis(id: number) {
  return request<{ ok: boolean; deleted: BrainAnalysisDetail }>(
    `/api/brain-analyses/${id}`,
    { method: 'DELETE' },
  )
}

export type StreamSessionStatus = 'running' | 'done' | 'error' | 'cancelled'

export interface StreamSession {
  id: string
  scope: string
  task_key: string
  status: StreamSessionStatus
  raw_content: string
  reasoning_content: string
  meta: Record<string, unknown>
  error: string
  created_at: string
  updated_at: string
  parsed_result?: Record<string, unknown>
}

export function createStreamSession(body: {
  scope: string
  task_key: string
  meta?: Record<string, unknown>
}) {
  return request<StreamSession>('/api/stream-sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function patchStreamSession(
  sessionId: string,
  patch: {
    raw_content?: string
    reasoning_content?: string
    status?: StreamSessionStatus
    error?: string
    parsed_result?: Record<string, unknown>
  },
) {
  return request<StreamSession>(`/api/stream-sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function getStreamSession(sessionId: string) {
  return request<StreamSession>(`/api/stream-sessions/${sessionId}`)
}

export async function getActiveStreamSession(scope: string, taskKey: string) {
  const search = new URLSearchParams({ scope, task_key: taskKey })
  try {
    return await request<StreamSession>(`/api/stream-sessions/active?${search.toString()}`)
  } catch {
    return null
  }
}
