#!/usr/bin/env python3
"""Tiny deterministic task planner; no LLM calls. Python 3.10+.
Plans are explicit user-editable JSON. Each task has a checkpoint and dependencies.
"""
import argparse, json, os, re, sys, uuid
from pathlib import Path
from datetime import datetime, timezone

def now(): return datetime.now(timezone.utc).isoformat()
def write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(tmp,path)
def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
def folder(): return Path('.opencode/slim-context')
def path_for(id):return folder()/'plans'/f'{id}.json'
def all_tasks():
    return sorted((read(p) for p in (folder()/'plans').glob('*.json')),key=lambda t:t['id'])
def init(args):
    f=folder();f.mkdir(parents=True,exist_ok=True)
    s=f/'state.json'
    if s.exists():print('State exists, keeping unchanged:',s);return
    write(s,dict(objective=args.objective,created=now(),updated=now(),decisions=[],notes=[],current_task=None))
    print('Initialized',f)
def add(args):
    if not (folder()/'state.json').exists():sys.exit('Run init first')
    tasks=all_tasks()
    id=f'{len(tasks)+1:03d}'
    deps=[x.strip() for x in args.after.split(',') if x.strip()]
    if any(x not in {t['id'] for t in tasks} for x in deps):sys.exit('Unknown dependency')
    task=dict(id=id,title=args.title,description=args.description or '',depends_on=deps,status='pending',
              files=args.files or [],acceptance=args.acceptance or [],model_hint=args.model or 'auto',
              attempts=0,evidence=[],created=now(),updated=now())
    write(path_for(id),task)
    print('Added',id,args.title)
def ready():
    tasks=all_tasks();done={t['id'] for t in tasks if t['status']=='done'}
    return [t for t in tasks if t['status'] in ('pending','active') and set(t['depends_on'])<=done]
def nexttask(args):
    tasks=ready()
    if not tasks: print('No ready tasks');return
    t=tasks[0]
    if args.activate:
        t['status']='active';t['updated']=now();t['attempts']+=1;write(path_for(t['id']),t)
        s=read(folder()/'state.json',{})
        s['current_task']=t['id'];s['updated']=now();write(folder()/'state.json',s)
    print(json.dumps(t,ensure_ascii=False,indent=2))
def finish(args):
    t=read(path_for(args.id))
    if not t:sys.exit('Task not found')
    if not args.evidence:sys.exit('Provide --evidence (test, commit, or check result)')
    t['status']='done';t['evidence'].append(args.evidence);t['updated']=now();write(path_for(args.id),t)
    s=read(folder()/'state.json',{});s['current_task']=None;s['updated']=now();write(folder()/'state.json',s)
    print('Completed',args.id)
def status(args):
    s=read(folder()/'state.json',{})
    print('OBJECTIVE:',s.get('objective','(not initialized)'))
    for t in all_tasks():print(f"{t['id']}  {t['status']:8}  {t['title']}  depends={','.join(t['depends_on'])}")
def brief(args):
    s=read(folder()/'state.json',{})
    tasks=all_tasks()
    current=ready()[:1]
    content=['# Work checkpoint',f"Objective: {s.get('objective','')}",
             'Completed: '+('; '.join(t['id']+': '+t['title'] for t in tasks if t['status']=='done') or 'none'),
             'Important decisions: '+('; '.join(s.get('decisions',[])) or 'none'),
             'Next task: '+(json.dumps(current[0],ensure_ascii=False) if current else 'none'),
             'Read exact source files and run tests; this brief is not proof of task completion.']
    result='\n'.join(content)
    if args.output:Path(args.output).write_text(result+'\n',encoding='utf-8')
    else:print(result)
def main():
    p=argparse.ArgumentParser();sp=p.add_subparsers(dest='cmd',required=True)
    a=sp.add_parser('init');a.add_argument('objective');a.set_defaults(fn=init)
    a=sp.add_parser('add');a.add_argument('title');a.add_argument('--description');a.add_argument('--after',default='');a.add_argument('--file',dest='files',action='append');a.add_argument('--acceptance',action='append');a.add_argument('--model');a.set_defaults(fn=add)
    a=sp.add_parser('next');a.add_argument('--activate',action='store_true');a.set_defaults(fn=nexttask)
    a=sp.add_parser('done');a.add_argument('id');a.add_argument('--evidence',required=True);a.set_defaults(fn=finish)
    a=sp.add_parser('status');a.set_defaults(fn=status)
    a=sp.add_parser('brief');a.add_argument('--output');a.set_defaults(fn=brief)
    args=p.parse_args();args.fn(args)
if __name__=='__main__':main()
