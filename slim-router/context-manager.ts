import type { Plugin } from '@opencode-ai/plugin'
import { readFileSync, writeFileSync, mkdirSync, existsSync, appendFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { homedir } from 'node:os'

// Additive OpenCode V1 plugin: checkpoints, conservative context warnings,
// deterministic context pruning and compaction-context injection.
// No unsupervised writes to source files and no background model requests.
type Cfg = {
  enabled: boolean; context_dir: string; warning_ratio: number;
  safe_local_ratio: number; reserve_output_tokens: number;
  model_context: Record<string,number>; auto_prune: boolean;
  auto_compact: boolean; max_tool_chars: number; log_file: string;
}
const defaults: Cfg = {
  enabled:true, context_dir:'.opencode/slim-context', warning_ratio:0.7,
  safe_local_ratio:0.72, reserve_output_tokens:4096,
  model_context:{'ananta-local/ananta-code-27b':32768},
  auto_prune:false, auto_compact:false, max_tool_chars:12000,
  log_file:'/tmp/opencode-slim-context.log',
}
const stamp = () => new Date().toISOString()
const safeWrite = (file:string, obj:unknown) => {
  mkdirSync(resolve(file,'..'),{recursive:true})
  const temp=file+'.tmp'; writeFileSync(temp,JSON.stringify(obj,null,2)+'\n');
  // Atomic replacement on same filesystem.
  requireRename(temp,file)
}
import { renameSync } from 'node:fs'
function requireRename(a:string,b:string) {renameSync(a,b)}
export const SlimContext:Plugin = async ({client,directory}) => {
  const configFile=join(process.env.HOME||homedir(),'.config/opencode/slim-context.json')
  let cfg:Cfg=defaults
  try { if(existsSync(configFile)) cfg={...defaults,...JSON.parse(readFileSync(configFile,'utf8'))} }
  catch(e) { console.error('[slim-context] config invalid',e); return {} }
  if(!cfg.enabled) return {}
  const root=resolve(directory,cfg.context_dir)
  const checkpointRoot=join(root,'checkpoints')
  mkdirSync(checkpointRoot,{recursive:true})
  const writeLog=(s:string)=>{try{appendFileSync(cfg.log_file,stamp()+' '+s+'\n')}catch{}}
  const lastNotified=new Map<string,number>()
  const getSnapshot=async(sessionID:string)=>{
    const result:any=await client.session.messages({path:{id:sessionID}})
    const msgs:any[]=result?.data??[]
    const last=msgs.at(-1)
    const model=last?.info?.model?.providerID && last?.info?.model?.modelID
      ? `${last.info.model.providerID}/${last.info.model.modelID}`
      : last?.info?.providerID && last?.info?.modelID
        ? `${last.info.providerID}/${last.info.modelID}` : undefined
    // Usage is not always present and may only describe a single message.
    const usage=msgs.filter(m=>m.info?.role==='assistant').at(-1)?.info?.tokens
    const currentInput=(usage?.input??0)+(usage?.cache?.read??0)
    return { sessionID, lastModel:model, latestReportedInputTokens:currentInput,
      messageCount:msgs.length, reportedUsageIsEstimate:true,
      lastUserTask:[...msgs].reverse().find(m=>m.info?.role==='user')?.parts
         ?.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n').slice(0,3000)??'',
      updatedAt:stamp() }
  }
  const snapshot=async(sessionID:string)=>{
    try {
      const state=await getSnapshot(sessionID)
      safeWrite(join(checkpointRoot,encodeURIComponent(sessionID)+'.json'),state)
      return state
    } catch(e) {writeLog(`checkpoint failed ${sessionID} ${String(e)}`);return null}
  }
  const warn=async(sessionID:string)=>{
    const state=await snapshot(sessionID)
    if(!state||!state.lastModel)return
    const limit=cfg.model_context[state.lastModel]
    if(!limit||!state.latestReportedInputTokens)return
    const ratio=(state.latestReportedInputTokens+cfg.reserve_output_tokens)/limit
    const prior=lastNotified.get(sessionID)??0
    if(ratio>=cfg.warning_ratio && Date.now()-prior>60000){
      lastNotified.set(sessionID,Date.now())
      writeLog(`CONTEXT_WARN session=${sessionID} model=${state.lastModel} ratio=${ratio.toFixed(3)} inputApprox=${state.latestReportedInputTokens} limit=${limit}; /compact manually`)
      try {await client.tui.showToast({body:{title:'Context budget',message:`${Math.round(ratio*100)}% inklusive Output-Reserve – /compact prüfen`,variant:'warning'}})}catch{}
    }
  }
  return {
    event:async({event}:any)=>{
      const p=event.properties??{}
      if(event.type==='session.idle'||(event.type==='session.status'&&p.status?.type==='idle')){
        const id=p.sessionID;if(id)await warn(id)
      }
      if(event.type==='session.compacted'&&p.sessionID) {
        writeLog(`COMPACTED session=${p.sessionID}`)
        await snapshot(p.sessionID)
      }
      if(event.type==='session.error'&&p.sessionID) {
        writeLog(`ERROR session=${p.sessionID} ${String(p.error?.data?.message??p.error?.name??'unknown').slice(0,250)}`)
        await snapshot(p.sessionID)
      }
    },
    // Context is attached only when OpenCode itself performs compaction.
    'experimental.session.compacting':async({sessionID}:any,output:any)=>{
      const state=await snapshot(sessionID)
      if(!state)return
      const planPath=join(root,'state.json')
      let plan=''
      try{plan=existsSync(planPath)?readFileSync(planPath,'utf8').slice(0,9000):''}catch{}
      output.context.push(
        'Preserve objective, decisions, unresolved issues, verified changes, tests, next steps, and important paths. Do not claim unverified completion. '+
        'Preserve pointers to external plan files and do not repeat long tool output. '+
        (plan?'Persistent plan state: '+plan:'')
      )
      writeLog(`COMPACTING session=${sessionID} addedPlanState=${Boolean(plan)}`)
    },
    // Pruning is opt-in because transforming history may break tool-call pairing.
    ...(cfg.auto_prune ? {
      'experimental.chat.messages.transform':async(_input:any,output:any)=>{
        const messages:any[]=output.messages??[]
        // Only shorten old, *completed* tool-result text; never delete tool events.
        for(const m of messages.slice(0,-8))for(const p of m.parts??[]){
          if(p.type==='tool'&&p.state?.status==='completed'&&typeof p.state?.output==='string'&&p.state.output.length>cfg.max_tool_chars){
            const src=p.state.output
            p.state.output=src.slice(0,2000)+`\n[slim-context: ${src.length-4000} middle characters omitted]\n`+src.slice(-2000)
          }
        }
      },
    }:{}),
  }
}
export default SlimContext
