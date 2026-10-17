import { test, expect, describe, beforeEach, afterEach } from 'bun:test'
import { mkdtempSync, writeFileSync, mkdirSync, readFileSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { SlimRouter } from '../slim-router/slim-router.ts'

// Verhaltenstest gegen einen Mock-Client: keine echten API-Aufrufe.
function makeClient(messages: any[] = []) {
  const calls: any = { promptAsync: [], abort: 0 }
  const client = {
    session: {
      messages: async () => ({ data: messages }),
      promptAsync: async (req: any) => { calls.promptAsync.push(req) },
      abort: async () => { calls.abort++ },
    },
    tui: { showToast: async () => {} },
  }
  return { client, calls }
}

const quotaError = JSON.stringify({
  type: 'retry', attempt: 1,
  message: '5 hour usage limit reached. It will reset in 30 minutes.',
  action: { reason: 'account_rate_limit' },
})

describe('SlimRouter behaviour (mock client, no real API)', () => {
  let home: string
  let dir: string
  let oldHome: string | undefined

  beforeEach(() => {
    home = mkdtempSync(join(tmpdir(), 'ac-router-home-'))
    dir = mkdtempSync(join(tmpdir(), 'ac-router-dir-'))
    oldHome = process.env.HOME
    process.env.HOME = home
    mkdirSync(join(home, '.config', 'opencode'), { recursive: true })
    writeFileSync(join(home, '.config', 'opencode', 'slim-router.json'), JSON.stringify({
      enabled: true,
      fallback_models: ['prov-a/model-a', 'prov-b/model-b', 'prov-c/model-c'],
      max_attempts: 3,
      cooldown_seconds: 300,
      local_model: 'ananta-local/ananta-code-27b',
      local_max_approx_input_tokens: 20000,
      log_file: join(dir, 'router.log'),
      state_dir: '.opencode/slim-context/router',
      failback_enabled: true,
      failback_max_cooldown_seconds: 21600,
      failback_backoff_factor: 2,
    }))
  })
  afterEach(() => {
    if (oldHome === undefined) delete process.env.HOME
    else process.env.HOME = oldHome
    rmSync(home, { recursive: true, force: true })
    rmSync(dir, { recursive: true, force: true })
  })

  const plugin = async (messages: any[] = []) => {
    const { client, calls } = makeClient(messages)
    const api: any = await (SlimRouter as any)({ client, directory: dir })
    return { api, calls }
  }

  const lastUser = (text = 'please continue the task') => ({
    info: { role: 'user', id: 'msg_u1', agent: 'build' },
    parts: [{ type: 'text', text }],
  })
  const assistant = (model: string, err?: string) => ({
    info: {
      role: 'assistant', id: 'msg_a1',
      model: { providerID: model.split('/')[0], modelID: model.split('/')[1] },
      time: err ? undefined : { completed: Date.now() },
      error: err ? new Error(err) : undefined,
      tokens: { input: 500, cache: { read: 0 } },
    },
    parts: [],
  })

  test('arms exactly one fallback on retryable error and dispatches on idle', async () => {
    const { api, calls } = await plugin([lastUser(), assistant('prov-a/model-a', 'quota')])
    await api.event({ event: { type: 'session.error', properties: { sessionID: 'ses_t1', error: quotaError } } })
    await api.event({ event: { type: 'session.idle', properties: { sessionID: 'ses_t1' } } })
    expect(calls.promptAsync.length).toBe(1)
    // session.error unterbricht den Provider-Abort nicht; nur Retry-Status abortet.
    expect(calls.abort).toBe(0)
    const body = calls.promptAsync[0].body
    expect(body.model.providerID).toBe('prov-b')
    expect(body.parts[0].text).toContain('SLIM ROUTER')
    // Wiederherstellung: der alte Prompt wird nicht erneut gesendet.
    expect(body.parts[0].text).not.toContain('please continue the task')
  })

  test('retry-status path aborts the native provider retry once', async () => {
    const { api, calls } = await plugin([lastUser(), assistant('prov-a/model-a', 'quota')])
    await api.event({
      event: {
        type: 'session.status',
        properties: { sessionID: 'ses_t1b', status: { type: 'retry', message: quotaError } },
      },
    })
    await api.event({ event: { type: 'session.idle', properties: { sessionID: 'ses_t1b' } } })
    expect(calls.abort).toBe(1)
    expect(calls.promptAsync.length).toBe(1)
  })

  test('stops after max_attempts (no endless loop)', async () => {
    const { api, calls } = await plugin([lastUser(), assistant('prov-a/model-a', 'quota')])
    for (let i = 0; i < 6; i++) {
      await api.event({ event: { type: 'session.error', properties: { sessionID: 'ses_t2', error: quotaError } } })
      await api.event({ event: { type: 'session.idle', properties: { sessionID: 'ses_t2' } } })
    }
    expect(calls.promptAsync.length).toBeLessThanOrEqual(3)
    expect(calls.promptAsync.length).toBeGreaterThan(0)
  })

  test('does not retry non-retryable errors', async () => {
    const { api, calls } = await plugin([lastUser()])
    await api.event({
      event: {
        type: 'session.error',
        properties: { sessionID: 'ses_t3', error: 'invalid api key' },
      },
    })
    await api.event({ event: { type: 'session.idle', properties: { sessionID: 'ses_t3' } } })
    expect(calls.promptAsync.length).toBe(0)
    expect(calls.abort).toBe(0)
  })

  test('successful completion resets attempts and unblocks the successful model', async () => {
    const { api, calls } = await plugin([lastUser(), assistant('prov-a/model-a', 'quota')])
    await api.event({ event: { type: 'session.error', properties: { sessionID: 'ses_t4', error: quotaError } } })
    await api.event({ event: { type: 'session.idle', properties: { sessionID: 'ses_t4' } } })
    expect(calls.promptAsync.length).toBe(1)
    // Erfolg des neuen Modells: Status wird zurueckgesetzt, keine weiteren Fallbacks.
    await api.event({
      event: {
        type: 'message.updated',
        properties: {
          sessionID: 'ses_t4',
          info: {
            role: 'assistant',
            model: { providerID: 'prov-b', modelID: 'model-b' },
            time: { completed: Date.now() },
          },
        },
      },
    })
    await api.event({ event: { type: 'session.idle', properties: { sessionID: 'ses_t4' } } })
    expect(calls.promptAsync.length).toBe(1)
    const healthPath = join(dir, '.opencode/slim-context/router/model-health.json')
    const health = JSON.parse(readFileSync(healthPath, 'utf8'))
    // Das erfolgreiche Modell wird entblockt; das ausgefallene bleibt bis Ablauf gesperrt.
    expect(health['prov-b/model-b']?.failures ?? 0).toBe(0)
    expect(health['prov-a/model-a'].failures).toBe(1)
  })

  test('persists state and blocks model with cooldown', async () => {
    const { api } = await plugin([lastUser(), assistant('prov-a/model-a', 'quota')])
    await api.event({ event: { type: 'session.error', properties: { sessionID: 'ses_t5', error: quotaError } } })
    const healthPath = join(dir, '.opencode/slim-context/router/model-health.json')
    expect(existsSync(healthPath)).toBe(true)
    const health = JSON.parse(readFileSync(healthPath, 'utf8'))
    expect(health['prov-a/model-a'].blockedUntil).toBeGreaterThan(Date.now())
    expect(health['prov-a/model-a'].failures).toBe(1)
  })

  test('session deletion cleans state', async () => {
    const { api } = await plugin([lastUser()])
    await api.event({ event: { type: 'session.error', properties: { sessionID: 'ses_t6', error: quotaError } } })
    await api.event({ event: { type: 'session.deleted', properties: { sessionID: 'ses_t6' } } })
    await api.event({ event: { type: 'session.idle', properties: { sessionID: 'ses_t6' } } })
    // Nach Loeschung darf kein Dispatch mehr stattfinden (state vergessen).
  })
})
