import type { Plugin } from '@opencode-ai/plugin'
import { existsSync, readFileSync, writeFileSync, mkdirSync, renameSync, appendFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'

// OpenCode 1.x plugin. Model routing is deterministic and uses no LLM calls.
// Recovery is a NEW continuation message, never a replay of the old user prompt.
const defaults = {
  enabled: true,
  fallback_models: [
    'xiaomi-token-plan-ams/mimo-v2.6-pro',
    'zai-coding-plan/glm-5.3',
    'opencode-go/kimi-k3',
    'opencode-go/deepseek-v4.1-flash',
    'ananta-local/ananta-code-27b',
    'opencode/deepseek-v4.1-flash-free',
    'opencode/glm-5.3-flash-free',
    'opencode/mimo-v2.6-flash-free',
  ],
  retryable_patterns: ['usage limit', 'quota', 'rate limit', 'too many requests', 'insufficient balance', 'no resource package', 'overloaded', 'service unavailable', 'timeout', 'econnreset', 'fetch failed'],
  max_attempts: 7,
  cooldown_seconds: 300,
  local_model: 'ananta-local/ananta-code-27b',
  local_max_approx_input_tokens: 20000,
  log_file: join(process.env.HOME || homedir(), '.local/state/opencode-slim-router.log'),
  state_dir: '.opencode/slim-context/router',
  failback_enabled: true,
  failback_max_cooldown_seconds: 21600,
  failback_backoff_factor: 2,
}
type Config = typeof defaults
interface State { tried: string[]; pending?: string; busy: boolean; lastError?: string; lastModel?: string; lastDispatchAt?: number; errorAt?: number; attempts?: number }
interface Health { blockedUntil:number; failures:number; reason:string; lastSuccess?:number }
const modelFrom = (m: any) => { const x = m?.info ?? m; const p = x?.providerID ?? x?.model?.providerID; const id = x?.modelID ?? x?.model?.modelID; return p && id ? `${p}/${id}` : undefined }
const modelArg = (model: string) => { const i = model.indexOf('/'); return { providerID: model.slice(0,i), modelID: model.slice(i+1) } }
const stringify = (o: any) => { try {return JSON.stringify(o ?? {})} catch {return String(o)} }
const iso = () => new Date().toISOString()
// HOME-Vorrang: respektiert Umgebungsueberschreibungen (Tests, Container, WSL).
const userHome = () => process.env.HOME || homedir()

// Recognise explicit reset/retry windows without blindly retrying during a quota lock.
// Guard: the OpenCode plugin loader invokes named exports with the plugin context (or no
// argument) and collects the return values in its hook list. A return of undefined/null
// makes the loader crash later ("plugin config hook failed"). Non-string input therefore
// returns 0 = "no explicit reset window"; the string path is unchanged for real callers.
export const resetDelayMs = (raw:string):number|undefined => {
  if (typeof raw !== 'string') return 0
  const text=raw.toLowerCase()
  const sections=text.match(/(?:reset|retry(?:ing)?|available)[^\n]{0,95}/g) ?? []
  for (const part of sections) {
    const h=part.match(/(\d+)\s*(?:hours?|hrs?|h)(?![a-z])/)
    const m=part.match(/(\d+)\s*(?:minutes?|mins?|m)(?![a-z])/)
    const sec=part.match(/(\d+)\s*(?:seconds?|secs?|s)(?![a-z])/)
    const duration=(h?Number(h[1])*3600:0)+(m?Number(m[1])*60:0)+(sec?Number(sec[1]):0)
    if (duration>0) return duration*1000
  }
  return undefined
}

const NON_RETRYABLE = /context (size|length|window)|too (many|long) tokens|maximum context|abortederror|messageabortederror|user cancelled|invalid api key|unauthorized/
const HTTP_RETRYABLE = /(?:status(?:code)?|http)[^\d]{0,6}(?:429|500|502|503|504|529)(?!\d)/

// Deterministic failure classification; no LLM call.
// Guard: same loader contract as resetDelayMs – a non-string raw is not a failure.
export const isRetryableFailure = (raw:string, patterns: readonly string[] = defaults.retryable_patterns):boolean => {
  if (typeof raw !== 'string') return false
  const s=raw.toLowerCase()
  if (NON_RETRYABLE.test(s)) return false
  return patterns.some(p=>s.includes(p.toLowerCase())) || HTTP_RETRYABLE.test(s)
}

// Cooldown for a failed model: explicit provider reset time wins, else capped exponential backoff.
export const cooldownMs = (failures:number, raw:string, cfg:{cooldown_seconds:number;failback_backoff_factor:number;failback_max_cooldown_seconds:number} = defaults):number => {
  if (typeof cfg?.cooldown_seconds !== 'number') cfg = defaults
  if (typeof failures !== 'number' || !Number.isFinite(failures)) failures = 1
  const baseMs=cfg.cooldown_seconds*1000
  const escalating=baseMs*Math.pow(cfg.failback_backoff_factor,Math.min(Math.max(failures-1,0),8))
  const explicit=resetDelayMs(raw)
  return explicit!==undefined ? explicit+60_000 : Math.min(cfg.failback_max_cooldown_seconds*1000,escalating)
}

export const SlimRouter: Plugin = async ({client, directory}) => {
  const cfgPath = join(userHome(), '.config/opencode/slim-router.json')
  let config: Config = defaults
  try { if (existsSync(cfgPath)) config = { ...defaults, ...JSON.parse(readFileSync(cfgPath,'utf8')) } }
  catch (e) { console.error('[slim-router] Invalid config:',e); return {} }
  if (!config.enabled) return {}
  const states = new Map<string,State>()
  // Persistent, per-provider cooldowns survive an OpenCode restart.
  const base = resolve(directory,config.state_dir)
  const healthFile = join(base, 'model-health.json')
  const health: Record<string, Health> = {}
  mkdirSync(base,{recursive:true})
  mkdirSync(resolve(config.log_file,'..'),{recursive:true})
  const log = (s:string) => { try { appendFileSync(config.log_file, `${iso()} ${s}\n`) } catch(e){console.error('[slim-router]',s,e)} }
  try { if (existsSync(healthFile)) Object.assign(health, JSON.parse(readFileSync(healthFile, 'utf8'))) } catch {}
  const saveHealth = () => {
    const tmp=healthFile+'.tmp'
    writeFileSync(tmp, JSON.stringify(health,null,2)+'\n')
    renameSync(tmp,healthFile)
  }
  // Recognise explicit reset/retry windows without blindly retrying during a 5-hour quota lock.
  const blockModel = (model:string,raw:string) => {
    const old=health[model] ?? {blockedUntil:0,failures:0,reason:''}
    const failures=old.failures+1
    // Explicit provider reset times are respected; unknown failures use capped exponential backoff.
    const delay=cooldownMs(failures, raw, config)
    health[model]={...old,failures,blockedUntil:Date.now()+delay,reason:raw.slice(0,250)}
    saveHealth()
    log(`BLOCK ${model} until=${new Date(health[model].blockedUntil).toISOString()} failures=${failures}`)
  }
  const available = (model:string) => (health[model]?.blockedUntil??0)<=Date.now()

  const save = (id:string, state:State) => {
    const file=join(base,encodeURIComponent(id)+'.json'); const tmp=file+'.tmp'
    writeFileSync(tmp, JSON.stringify({sessionID:id,...state,updatedAt:iso()},null,2)+'\n'); renameSync(tmp,file)
  }
  const stateFor = (id:string) => {
    if (!states.has(id)) {
      let state:State={tried:[],busy:false}
      const file=join(base,encodeURIComponent(id)+'.json')
      try { if(existsSync(file)) {const old=JSON.parse(readFileSync(file,'utf8')); state={...state,...old,busy:false,pending:undefined}} } catch{}
      states.set(id,state)
    }
    return states.get(id)!
  }
  const failure = (raw:string) => isRetryableFailure(raw, config.retryable_patterns)
  async function getMessages(id:string):Promise<any[]> {const response:any=await client.session.messages({path:{id}}); return response?.data ?? []}
  async function propose(id:string, raw:string) {
    if (!failure(raw)) return
    const st=stateFor(id)
    if(st.pending || st.busy || (st.attempts??0)>=config.max_attempts) return
    const msgs=await getMessages(id)
    const assistant=[...msgs].reverse().find(m=>m.info?.role==='assistant')
    const from=st.lastModel ?? modelFrom(assistant)
    if(from) blockModel(from,raw)
    const usage=assistant?.info?.tokens
    const input=(usage?.input??0)+(usage?.cache?.read??0)
    const localSafe=input>0 && input<=config.local_max_approx_input_tokens
    // ALWAYS rescan from preferred model at each failure, but avoid a blocked model.
    // No spontaneous background call is sent just to probe availability.
    const next=config.fallback_models.find(m=>m!==from && available(m) && (config.failback_enabled || !st.tried.includes(m)) && (m!==config.local_model || localSafe))
    if(!next){log(`${id} no available fallback; next expiry=${Object.entries(health).filter(([_,v])=>v.blockedUntil>Date.now()).sort((a,b)=>a[1].blockedUntil-b[1].blockedUntil)[0]?.[0]??'none'}`);save(id,st);return}
    st.pending=next;st.errorAt=Date.now();st.lastError=raw.slice(0,500);st.attempts=(st.attempts??0)+1
    if(!st.tried.includes(from??'')) st.tried.push(from??'unknown')
    save(id,st)
    log(`${id} fallback ${from??'unknown'} -> ${next} attempt=${st.attempts}, reason=${raw.slice(0,180)}`)
  }
  async function dispatch(id:string) {
    const s=stateFor(id)
    if(!s.pending || s.busy) return
    const next=s.pending
    s.pending=undefined;s.busy=true;s.tried.push(next);s.lastModel=next;save(id,s)
    try {
      const msgs=await getMessages(id)
      const lastUser=[...msgs].reverse().find(m=>m.info?.role==='user')
      if(!lastUser){log(`${id} no last user prompt, stopped`);return}
      const agent=lastUser.info?.agent || 'build'
      const planPath=resolve(directory,'.opencode/slim-context/state.json')
      let plan=''
      try {if(existsSync(planPath))plan=readFileSync(planPath,'utf8').slice(0,8000)}catch{}
      // New instruction rather than replay: agent must inspect progress and avoid duplicate side effects.
      const prompt=[
        '[SLIM ROUTER: PROVIDER RECOVERY]',
        'The previous model invocation failed. Continue the EXISTING user task using the current conversation and repository state.',
        'FIRST inspect the latest assistant/tool results and actual changed files. Do not repeat completed edits, shell commands, commits, or external actions.',
        'If prior tool execution is uncertain, inspect state and verify before proceeding. Ask for confirmation before any non-idempotent external action.',
        'Carry out only unfinished steps, run appropriate checks, and summarize what was verified.',
        plan ? `Persistent task plan (may be stale; verify against files):\n${plan}` : '',
      ].filter(Boolean).join('\n\n')
      log(`${id} dispatch fallback model=${next} agent=${agent}`)
      await client.session.promptAsync({path:{id},body:{agent,model:modelArg(next),parts:[{type:'text',text:prompt}]}})
      s.lastDispatchAt=Date.now()
      log(`${id} fallback prompt accepted ${next}`)
    }catch(e){log(`${id} fallback dispatch rejected: ${stringify(e).slice(0,700)}`)}
    finally{s.busy=false;save(id,s)}
  }
  log('INITIALIZED')
  return {
    event: async ({event}:any)=>{
      const p=event.properties??{}; const id=p.sessionID ?? p.info?.id
      if(!id)return
      if(event.type==='session.deleted'){states.delete(id);return}
      if(event.type==='message.updated') {
        const info=p.info
        if(info?.role==='assistant' && info?.time?.completed && !info?.error) {
          const actual=modelFrom(info)
          const st=stateFor(id)
          if(actual && actual===st.lastModel && !st.pending) {
            st.attempts=0;st.tried=[];save(id,st)
            if(health[actual]) {health[actual].failures=0;health[actual].blockedUntil=0;health[actual].lastSuccess=Date.now();saveHealth()}
          }
        }
        return
      }
      if(event.type==='session.error') {try{await propose(id,stringify(p.error))}catch(e){log(`${id} error-handler: ${String(e)}`)};return}
      if(event.type==='session.status' && p.status?.type==='retry') {
        // Quota wait: prepare replacement, then cancel native long retry.
        // Abort moves session to idle, which dispatches exactly one continuation prompt.
        const raw=stringify(p.status)
        if (!failure(raw)) return
        try {
          await propose(id, raw)
          const st=stateFor(id)
          if (st.pending && !st.busy) {
            log(`${id} aborting provider retry; pending=${st.pending}`)
            await client.session.abort({path:{id}})
          }
        } catch(e) {log(`${id} retry error: ${String(e)}`)}
        return
      }
      if(event.type==='session.idle'||(event.type==='session.status'&&p.status?.type==='idle')) {
        const s=stateFor(id)
        if(s.pending) {await dispatch(id);return}
        // Completion may be a previous failure; don't reset until evidence of success.
      }
    },
  }
}

export default SlimRouter
