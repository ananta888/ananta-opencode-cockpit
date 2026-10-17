import base64
import importlib.util
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from chat_runtime import list_chats
from chat_store import ChatStore
from commands import confirm, pick_session
from selection import Choice, pick

URL = 'http://127.0.0.1:4096'


def headers(project):
    result = {'Content-Type':'application/json', 'x-opencode-directory':project}
    password = os.environ.get('OPENCODE_SERVER_PASSWORD')
    if password:
        token = base64.b64encode((os.environ.get('OPENCODE_SERVER_USERNAME','opencode')+':'+password).encode()).decode()
        result['Authorization'] = 'Basic '+token
    return result


def ready():
    try:
        req = urllib.request.Request(URL+'/global/health', headers=headers(''))
        with urllib.request.urlopen(req, timeout=1) as response:
            return json.load(response).get('healthy') is True
    except (OSError, ValueError):
        return False


def ensure_server(project):
    if ready():
        return
    store = ChatStore()
    with store.lock('server'):
        if ready():
            return
        log = store.directory / 'server.log'
        with log.open('ab') as output:
            child = subprocess.Popen(['opencode','serve','--hostname','127.0.0.1','--port','4096'], cwd=project,
                                     stdout=output, stderr=output, start_new_session=True)
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            if ready():
                return
            if child.poll() is not None:
                raise RuntimeError(f'OpenCode-Server konnte nicht starten. Log: {log}')
            time.sleep(.15)
        raise RuntimeError(f'OpenCode-Server antwortet nicht. Log: {log}')


def request(project, method, path, body=None):
    ensure_server(project)
    separator = '&' if '?' in path else '?'
    url = URL+path+separator+urllib.parse.urlencode({'directory':project})
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 method=method, headers=headers(project))
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'OpenCode HTTP {error.code}: {error.read(300).decode(errors="replace")}') from error


def engine():
    root = Path(__file__).resolve().parent
    source = root/'side-sync.py'
    if not source.exists():
        source = root.parent/'oc-side-sync/side-sync.py'
    spec = importlib.util.spec_from_file_location('ananta_sync_engine', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProjectAPI:
    def __init__(self, project):
        self.project = project

    def messages(self, session):
        value = request(self.project, 'GET', '/session/'+urllib.parse.quote(session, safe='')+'/message')
        return value.get('data', value) if isinstance(value, dict) else value

    def status(self):
        value = request(self.project, 'GET', '/session/status')
        return value.get('data', value) if isinstance(value, dict) else value

    def post_note(self, session, text):
        return request(self.project, 'POST', '/session/'+urllib.parse.quote(session, safe='')+'/message',
                       {'noReply':True, 'parts':[{'type':'text','text':text}]})


def pair(project, chat, other=False):
    sides = [r for r in list_chats(project) if r['parent_id'] and r['session_id']]
    if chat and chat.get('parent_id') and chat.get('session_id') and not other:
        return chat['parent_id'], chat['session_id'], chat
    if sides and not other:
        value = pick('Side-Chat waehlen', [Choice(r['id'],r['title']+' '+r['session_id']) for r in sides])
        row = next((r for r in sides if r['id'] == value), None)
        if row:
            return row['parent_id'], row['session_id'], row
        return None
    main = chat.get('session_id') if chat else None
    main = main or pick_session('Quellchat waehlen')
    side = pick_session('Zielchat waehlen', excluded=main) if main else None
    return (main, side, None) if main and side else None


def execute(action, project, chat):
    chosen = pair(project, chat, action == 'context-other')
    if not chosen:
        return
    main, side, row = chosen
    direction = 'side-to-main' if action == 'context-to-main' else 'main-to-side'
    if action in ('context-preview', 'context-reset'):
        direction = pick('Richtung', [Choice('main-to-side','Main nach Side'), Choice('side-to-main','Side nach Main')])
        if not direction:
            return
    module = engine()
    statepath = module.statefile(main+'|'+side)
    lockname = 'sync-'+statepath.stem
    with ChatStore().lock(lockname):
        state = module.readstate(statepath)
        if action == 'context-status':
            print(json.dumps(state, indent=2))
            return
        if action == 'context-reset':
            if confirm('Cursor zuruecksetzen? Bereits uebertragene Texte koennen erneut erscheinen.'):
                state['seen'].pop(direction, None)
                module.save(statepath, state)
            return
        api = ProjectAPI(project)
        if action == 'context-init':
            if state['seen'] or state['pending']:
                raise RuntimeError('Sync wurde bereits initialisiert oder verwendet.')
            for name, sid in [('main-to-side', main), ('side-to-main', side)]:
                rows = [module.extract(m) for m in api.messages(sid)]
                rows = [r for r in rows if r and r['id']]
                if rows:
                    state['seen'][name] = rows[-1]['id']
            module.save(statepath, state)
            print('Ab jetzt werden nur neue Nachrichten uebertragen.')
            return
        if state['pending'].get(direction):
            raise RuntimeError('Ungeklaerte vorherige Uebertragung: Sync-Status und Zielchat pruefen.')
        source, target = (main, side) if direction == 'main-to-side' else (side, main)
        rows, cursor = module.payload(api, source, state['seen'].get(direction))
        if not rows:
            print('Keine neuen Texte vorhanden.')
            return
        note = module.make_note(rows, source, target, 2000)
        print(note)
        if action == 'context-preview' or not confirm('Diese Vorschau als Kontext uebertragen?'):
            return
        if module.busy(api, target):
            raise RuntimeError('Zielchat arbeitet gerade. Bitte spaeter erneut versuchen.')
        state['pending'][direction] = {'cursor':cursor,'target':target}
        module.save(statepath, state)
        api.post_note(target, note)
        state['seen'][direction] = cursor
        state['pending'].pop(direction, None)
        module.save(statepath, state)
        if row:
            ChatStore().update(row['id'], {'last_sync':time.strftime('%H:%M'), 'last_sync_direction':direction})
        print('Kontext uebertragen. Im Ziel wird keine Modellantwort gestartet.')
