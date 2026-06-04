import { md5 } from './md5'

const STORAGE_SALT = 'rp-chat-local-api-key'
const ENCRYPT_PREFIX = 'md5:'

function deriveKeyBytes(): Uint8Array {
  const origin = typeof window !== 'undefined' ? window.location.origin : 'rp-chat'
  const hex = md5(`${STORAGE_SALT}:${origin}`)
  const bytes = new Uint8Array(16)
  for (let i = 0; i < 16; i += 1) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16)
  }
  return bytes
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary)
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

/** 使用 MD5 派生密钥的可逆本地存储加密（非明文落盘）。 */
export function encryptSecret(plain: string): string {
  if (!plain) return ''
  const key = deriveKeyBytes()
  const plainBytes = new TextEncoder().encode(plain)
  const encrypted = new Uint8Array(plainBytes.length)
  for (let i = 0; i < plainBytes.length; i += 1) {
    encrypted[i] = plainBytes[i] ^ key[i % key.length]
  }
  return `${ENCRYPT_PREFIX}${bytesToBase64(encrypted)}`
}

export function decryptSecret(stored: string): string {
  if (!stored) return ''
  if (!stored.startsWith(ENCRYPT_PREFIX)) {
    return stored
  }
  try {
    const key = deriveKeyBytes()
    const encrypted = base64ToBytes(stored.slice(ENCRYPT_PREFIX.length))
    const plainBytes = new Uint8Array(encrypted.length)
    for (let i = 0; i < encrypted.length; i += 1) {
      plainBytes[i] = encrypted[i] ^ key[i % key.length]
    }
    return new TextDecoder().decode(plainBytes)
  } catch {
    return ''
  }
}

export function isEncryptedSecret(stored: string): boolean {
  return stored.startsWith(ENCRYPT_PREFIX)
}
