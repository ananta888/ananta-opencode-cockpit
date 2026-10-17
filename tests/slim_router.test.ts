import { test, expect, describe } from 'bun:test'
import { resetDelayMs, isRetryableFailure, cooldownMs } from '../slim-router/slim-router.ts'

describe('resetDelayMs', () => {
  test('parses hour+minute reset windows', () => {
    const raw = '5 hour usage limit reached. It will reset in 2 hours 27 minutes.'
    expect(resetDelayMs(raw)).toBe((2 * 3600 + 27 * 60) * 1000)
  })
  test('parses seconds', () => {
    expect(resetDelayMs('rate limit, retry in 30 seconds')).toBe(30_000)
  })
  test('returns undefined when no window is stated', () => {
    expect(resetDelayMs('service unavailable')).toBeUndefined()
    expect(resetDelayMs('quota exceeded')).toBeUndefined()
  })
  test('does not treat unrelated numbers as durations', () => {
    expect(resetDelayMs('error code 42 available in docs')).toBeUndefined()
  })
})

describe('isRetryableFailure', () => {
  test('recognises quota and rate-limit errors', () => {
    expect(isRetryableFailure('5 hour usage limit reached')).toBe(true)
    expect(isRetryableFailure('Too Many Requests')).toBe(true)
    expect(isRetryableFailure('insufficient balance')).toBe(true)
  })
  test('recognises HTTP status codes', () => {
    expect(isRetryableFailure('HTTP 429')).toBe(true)
    expect(isRetryableFailure('status code 503')).toBe(true)
    expect(isRetryableFailure('statusCode: 500')).toBe(true)
  })
  test('rejects non-retryable errors', () => {
    expect(isRetryableFailure('invalid api key')).toBe(false)
    expect(isRetryableFailure('unauthorized')).toBe(false)
    expect(isRetryableFailure('user cancelled')).toBe(false)
    expect(isRetryableFailure('context size exceeded')).toBe(false)
    expect(isRetryableFailure('too many tokens in prompt')).toBe(false)
    expect(isRetryableFailure('MessageAbortedError')).toBe(false)
  })
  test('rejects ordinary messages', () => {
    expect(isRetryableFailure('task completed successfully')).toBe(false)
    expect(isRetryableFailure('')).toBe(false)
  })
})

describe('cooldownMs', () => {
  const cfg = { cooldown_seconds: 300, failback_backoff_factor: 2, failback_max_cooldown_seconds: 21600 }
  test('uses explicit reset window plus grace', () => {
    const ms = cooldownMs(1, 'reset in 10 minutes', cfg)
    expect(ms).toBe(10 * 60 * 1000 + 60_000)
  })
  test('grows exponentially without reset hint', () => {
    expect(cooldownMs(1, 'service unavailable', cfg)).toBe(300_000)
    expect(cooldownMs(2, 'service unavailable', cfg)).toBe(600_000)
    expect(cooldownMs(3, 'service unavailable', cfg)).toBe(1_200_000)
  })
  test('is capped at failback_max_cooldown_seconds', () => {
    expect(cooldownMs(30, 'service unavailable', cfg)).toBe(21_600_000)
  })
  test('explicit window is used no matter the failure count (no lockout drift)', () => {
    const a = cooldownMs(1, 'reset in 1 hour', cfg)
    const b = cooldownMs(5, 'reset in 1 hour', cfg)
    expect(a).toBe(b)
    expect(a).toBe(3600 * 1000 + 60_000)
  })
})

describe('loop-safety regression (documented behaviour)', () => {
  test('non-retryable error must never arm a fallback', () => {
    // Guard: if this classification ever flips, the router would loop on
    // context-overflow errors and burn tokens.
    const samples = [
      'AbortError: user cancelled',
      'invalid api key',
      'context window exceeded',
    ]
    for (const s of samples) expect(isRetryableFailure(s)).toBe(false)
  })
})

describe('opencode loader contract (named exports are called with the plugin context)', () => {
  // The loader (Gy) calls the factory AND every named export with the plugin
  // context, collects the return values in its hook list and later invokes
  // hook.config(input). A return of undefined/null crashes that step with
  // "plugin config hook failed" and takes the provider config down with it.
  const ctx = { client: {}, directory: '/tmp', worktree: '/tmp' } as any
  const badInputs = [ctx, undefined, null, 42, {}, [] as any]

  test('resetDelayMs never throws and never returns undefined/null on loader input', () => {
    for (const bad of badInputs) {
      expect(() => resetDelayMs(bad as any)).not.toThrow()
      const r = resetDelayMs(bad as any)
      expect(r).not.toBeUndefined()
      expect(r).not.toBeNull()
    }
  })
  test('isRetryableFailure never throws and never returns undefined/null on loader input', () => {
    for (const bad of badInputs) {
      expect(() => isRetryableFailure(bad as any)).not.toThrow()
      const r = isRetryableFailure(bad as any)
      expect(r).not.toBeUndefined()
      expect(r).not.toBeNull()
    }
    expect(isRetryableFailure(ctx)).toBe(false)
  })
  test('cooldownMs never throws and returns a finite number on loader input', () => {
    for (const bad of badInputs) {
      expect(() => cooldownMs(bad as any, bad as any)).not.toThrow()
      const r = cooldownMs(bad as any, bad as any)
      expect(Number.isFinite(r)).toBe(true)
    }
  })
})
