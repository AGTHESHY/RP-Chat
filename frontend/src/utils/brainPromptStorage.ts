import { DEFAULT_BRAIN_SYSTEM_PROMPT } from '../constants/defaultBrainPrompt'

export const BRAIN_PROMPT_STORAGE_KEY = 'rp-chat-brain-system-prompt'

export function loadBrainSystemPrompt(): string {
  try {
    const raw = localStorage.getItem(BRAIN_PROMPT_STORAGE_KEY)
    if (raw && raw.trim()) return raw
  } catch {
    /* ignore */
  }
  return DEFAULT_BRAIN_SYSTEM_PROMPT
}

export function saveBrainSystemPrompt(prompt: string): void {
  localStorage.setItem(BRAIN_PROMPT_STORAGE_KEY, prompt)
}

export function resetBrainSystemPrompt(): string {
  localStorage.removeItem(BRAIN_PROMPT_STORAGE_KEY)
  return DEFAULT_BRAIN_SYSTEM_PROMPT
}

export { DEFAULT_BRAIN_SYSTEM_PROMPT }
