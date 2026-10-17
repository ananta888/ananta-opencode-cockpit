import json
import os
import shlex
import subprocess
from pathlib import Path

from chat_runtime import LaunchOptions, adopt_main, close_chat, focus_chat, host_context, launch_chat, list_chats, rename_chat
from commands import choose, confirm, list_sessions, pick_model, pick_session, run, run_capture
from selection import Choice, pick, select


def preferences(changes=None):
    path = Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'ananta-cockpit/preferences.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    if changes is not None:
        data.update(changes)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2))
        temporary.replace(path)
    return data


def pick_chat(project, side=False):
    rows = [r for r in list_chats(project) if not side or r['kind'] == 'side']
    value = pick('Chat waehlen', [Choice(r['id'], f"{r['title']} [{r['status']}] {r['session_id']}") for r in rows]) if rows else None
    return next((r for r in rows if r['id'] == value), None)


def parent_chat(project, chat):
    if chat and chat['session_id']:
        return chat
    sid = pick_session('Hauptsitzung auswaehlen')
    if sid:
        return adopt_main(project, sid, host_context()['host_main'])
    return None


def execute(action, project, chat):
    if action in ('chat-list', 'chat-close', 'chat-rename', 'chat-delete'):
        chat = chat or pick_chat(project)
        if not chat:
            return
        if action == 'chat-list':
            focus_chat(chat['id'])
        elif action == 'chat-close':
            close_chat(chat['id'])
        elif action == 'chat-rename':
            title = choose('Neuer Name: ')
            if title:
                from context_sync import request
                if chat['session_id']:
                    request(project, 'PATCH', '/session/'+chat['session_id'], {'title':title})
                rename_chat(chat['id'], title)
        elif confirm(f"Chat {chat['title']} unwiderruflich loeschen?"):
            result = run(['opencode','session','delete',chat['session_id']], cwd=project)
            if result and result.returncode == 0:
                close_chat(chat['id'])
    elif action in ('chat-new', 'chat-side', 'chat-resume'):
        parent = parent_chat(project, chat) if action == 'chat-side' else None
        if action == 'chat-side' and not parent:
            return
        sid = (chat.get('session_id') if chat else None) if action == 'chat-resume' else None
        if action == 'chat-resume' and not sid:
            sid = pick_session('Bestehenden Chat fortsetzen')
        if action == 'chat-resume' and not sid:
            return
        existing = next((r for r in list_chats(project) if sid and r['session_id'] == sid), None)
        if existing and existing['status'] not in ('closed', 'failed', 'exited', 'stopped'):
            focus_chat(existing['id'])
            return
        source = existing or parent or chat or {}
        launch_chat(LaunchOptions(project=project, parent_id=source.get('parent_id','') if sid else (parent['session_id'] if parent else ''),
                                  resume_id=sid, model=source.get('model') or preferences().get('model'),
                                  mcp=source.get('mcp', False), placement=preferences().get('placement','popup')))
    elif action == 'chat-cleanup':
        rows = [r for r in list_chats(project) if r['status'] in ('closed', 'failed', 'exited', 'stopped') and r['session_id']]
        ids = select('Gespeicherte Chats zum Loeschen markieren', [Choice(r['id'],r['title']+' '+r['session_id']) for r in rows], multiple=True) if rows else []
        if ids and confirm(f'{len(ids)} gespeicherte Chats unwiderruflich loeschen?'):
            for row in rows:
                if row['id'] in ids:
                    result = run(['opencode','session','delete',row['session_id']], cwd=project)
                    if result and result.returncode == 0:
                        from chat_store import ChatStore
                        ChatStore().update(row['id'], {'session_id':'','status':'deleted'})
    elif action.startswith('model-'):
        if action == 'model-change' and chat:
            subprocess.run(['tmux','send-keys','-t',chat['pane'],'C-x'], check=True)
            subprocess.run(['tmux','send-keys','-t',chat['pane'],'m'], check=True)
            focus_chat(chat['id'])
        else:
            favorites = preferences().get('favorites', [])
            model = pick('Modellfavoriten', [Choice(m,m) for m in favorites]) if action == 'model-favorites' and favorites else pick_model()
            if model:
                preferences({'model':model, 'favorites':list(dict.fromkeys([*favorites, model]))})
                print('Modell fuer neue Chats:', model)
    elif action.startswith('project-'):
        if action == 'project-folder':
            opener = 'explorer.exe' if os.environ.get('WSL_DISTRO_NAME') else 'xdg-open'
            run([opener, project])
            return
        history = preferences().get('projects', [])
        path = pick('Letzte Projekte', [Choice(p,p) for p in history]) if action == 'project-recent' and history else choose('Projektpfad: ')
        if not path:
            return
        directory = Path(path).expanduser().resolve()
        if action == 'project-new':
            directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise ValueError('Projektordner existiert nicht')
        preferences({'projects':list(dict.fromkeys([str(directory),*history]))[:20]})
        command = shlex.join(['bash', str(Path(__file__).with_name('cockpit')), 'up', str(directory), '--pane'])
        subprocess.run(['tmux','new-window','-c',str(directory),command], check=True)
