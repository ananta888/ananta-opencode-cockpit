"""Plan, router, CodeCompass and diagnostic command adapters."""
from __future__ import annotations

import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from .chat_runtime import LaunchOptions, current_chat, launch_chat
    from .commands import choose
except ImportError:
    from chat_runtime import LaunchOptions, current_chat, launch_chat
    from commands import choose


class ToolActionError(RuntimeError):
    """A tool action failed and its diagnostic should remain visible."""


def _config_root() -> Path:
    return Path(os.environ.get('OC_CONFIG_DIR') or Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'opencode')


def _run(argv: list[str], project: str) -> None:
    try:
        result = subprocess.run(argv, cwd=project, check=False)
    except OSError as error:
        raise ToolActionError(f'{argv[0]}: {error}') from error
    if result.returncode:
        raise ToolActionError(f'{argv[0]} beendet mit Exit {result.returncode}')


def _edit(path: Path, project: str, defaults: str = '{}\n') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(defaults)
    editor = shlex.split(os.environ.get('VISUAL') or os.environ.get('EDITOR') or 'vi')
    if not editor:
        raise ToolActionError('EDITOR ist leer')
    _run([*editor, str(path)], project)


def _read_config(path: Path) -> dict:
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict):
        raise ToolActionError(f'{path}: JSON-Objekt erwartet')
    return data


def _toggle(path: Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = _read_config(path)
        previous = config.get(key, True)
        if not isinstance(previous, bool):
            raise ToolActionError(f'{path}: {key} muss true oder false sein')
        config[key] = not previous
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(config, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    print(f'{key}: {str(config[key]).lower()}')
    print('Aenderung gilt fuer neu gestartete OpenCode-Sitzungen.')


def _plan(action: str, project: str) -> bool:
    command = ['slim-plan']
    if not shutil.which(command[0]):
        local = Path(__file__).resolve().parent.parent / 'slim-router/planctl.py'
        if not local.exists():
            raise ToolActionError('slim-plan ist nicht installiert')
        command = [sys.executable, str(local)]
    match action:
        case 'plans-open':
            args = ['status']
        case 'plans-new':
            objective = choose('Ziel des Plans: ')
            if not objective:
                return True
            args = ['init', objective]
        case 'plans-edit':
            title = choose('Aufgabentitel: ')
            if not title:
                return True
            args = ['add', title, '--description', choose('Beschreibung: ')]
        case 'plans-validate':
            args = ['next']
        case 'plans-activate':
            args = ['next', '--activate']
        case 'plans-brief':
            args = ['brief']
        case 'plans-done':
            task = choose('Aufgaben-ID: ')
            if not task:
                return True
            if not task.isdigit():
                raise ToolActionError('Aufgaben-ID muss numerisch sein')
            evidence = choose('Nachweis (Test, Commit oder Pruefergebnis): ')
            if not evidence:
                raise ToolActionError('Ein Nachweis ist erforderlich')
            args = ['done', task, '--evidence', evidence]
        case _:
            return False
    _run([*command, *args], project)
    return True


def _logs(project: str) -> None:
    state = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    candidates = [state / 'opencode-slim-router.log', Path('/tmp/opencode-slim-context.log')]
    candidates.extend((state / 'ananta-cockpit').glob('*.log'))
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    candidates.extend((data / 'opencode/log').glob('*.log'))
    for name in ('slim-router.json', 'slim-context.json'):
        configured = _read_config(_config_root() / name).get('log_file')
        if isinstance(configured, str):
            candidates.append(Path(configured).expanduser())
    found = sorted({path.resolve() for path in candidates if path.is_file()})
    for path in found:
        print(f'{path} ({path.stat().st_size} Bytes)')
    if not found:
        print('Keine Logdateien vorhanden.')


def execute(action: str, project: str) -> bool:
    """Return False only for unknown actions; command failures raise visibly."""
    if action.startswith('plans-'):
        return _plan(action, project)
    router = _config_root() / 'slim-router.json'
    match action:
        case 'router-toggle':
            _toggle(router, 'enabled')
        case 'router-failback':
            _toggle(router, 'failback_enabled')
        case 'router-status':
            config = _read_config(router)
            print(f'Konfiguration: {router}')
            for key in ('enabled', 'failback_enabled'):
                print(f'{key}: {config.get(key, True)}')
        case 'router-config':
            _edit(router, project)
        case 'context-config':
            _edit(_config_root() / 'slim-context.json', project)
        case 'context-snapshots':
            config = _read_config(_config_root() / 'slim-context.json')
            root = Path(project) / config.get('context_dir', '.opencode/slim-context')
            snapshots = sorted(root.rglob('*.json')) if root.exists() else []
            for path in snapshots:
                print(path)
            if not snapshots:
                print('Keine Kontext-Snapshots vorhanden.')
        case 'cc-config':
            config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'ananta-cockpit/codecompass.json'
            _edit(config, project, '{"hub_url": "http://127.0.0.1:5000", "server_name": "ananta_codecompass"}\n')
        case 'cc-status' | 'cc-tools' | 'cc-login':
            _run(['oc-codecompass', action.removeprefix('cc-')], project)
        case 'cc-start':
            chat = current_chat()
            launch_chat(LaunchOptions(project=project, parent_id=chat['session_id'] if chat else '',
                                      model=chat['model'] if chat else None, mcp=True))
        case 'logs':
            _logs(project)
        case 'diagnostics':
            print(f'Projekt: {Path(project).resolve()}')
            print(f'OpenCode-Konfiguration: {_config_root()}')
            for binary in ('tmux', 'opencode', 'oc-codecompass', 'slim-plan', 'oc-side-sync'):
                print(f'{binary}: {shutil.which(binary) or "nicht installiert"}')
            for name in ('slim-router.json', 'slim-context.json'):
                path = _config_root() / name
                _read_config(path)
                print(f'{name}: {"lesbar" if path.exists() else "nicht vorhanden"}')
        case _:
            return False
    return True
