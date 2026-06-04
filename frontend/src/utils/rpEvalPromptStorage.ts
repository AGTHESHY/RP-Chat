import { DEFAULT_RP_EVAL_SYSTEM_PROMPT } from '../constants/defaultRpEvalPrompt'

export const RP_EVAL_PROMPT_STORAGE_KEY = 'rp-chat-rp-eval-system-prompt'

export function loadRpEvalSystemPrompt(): string {
  try {
    const raw = localStorage.getItem(RP_EVAL_PROMPT_STORAGE_KEY)
    if (raw && raw.trim()) return raw
  } catch {
    /* ignore */
  }
  return DEFAULT_RP_EVAL_SYSTEM_PROMPT
}

export function saveRpEvalSystemPrompt(prompt: string): void {
  localStorage.setItem(RP_EVAL_PROMPT_STORAGE_KEY, prompt)
}

export function resetRpEvalSystemPrompt(): string {
  localStorage.removeItem(RP_EVAL_PROMPT_STORAGE_KEY)
  return DEFAULT_RP_EVAL_SYSTEM_PROMPT
}

export { DEFAULT_RP_EVAL_SYSTEM_PROMPT }
