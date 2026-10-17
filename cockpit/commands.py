import re
import subprocess

from selection import Choice, pick


def run(argv, cwd=None):
    try:
        return subprocess.run(argv, cwd=cwd, check=False, text=True, capture_output=False)
    except FileNotFoundError:
        print('Befehl nicht vorhanden:', argv[0])
        return None


def run_capture(argv, cwd=None):
    try:
        result = subprocess.run(argv, cwd=cwd, check=False, text=True, capture_output=True)
        return (result.stdout or '') + (result.stderr or '')
    except FileNotFoundError:
        return ''


def choose(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ''


def confirm(prompt):
    return pick(prompt, [Choice('no', 'Nein, abbrechen'),
                         Choice('yes', 'Ja, ausfuehren')]) == 'yes'


def list_sessions():
    out = run_capture(['opencode', 'session', 'list'])
    return list(dict.fromkeys(re.findall(r'ses_[A-Za-z0-9_-]+', out))), out


def session_choices(ids, out):
    return [Choice(sid, next((' '.join(line.split()) for line in out.splitlines()
                             if sid in line.split()), sid)) for sid in ids]


def pick_session(title, excluded=None):
    ids, out = list_sessions()
    choices = [choice for choice in session_choices(ids, out) if choice.value != excluded]
    if not choices:
        print('Keine passenden Sitzungen gefunden. Zuerst eine OpenCode-Sitzung starten.')
        return None
    return pick(title, choices)


def pick_model():
    default = 'xiaomi-token-plan-ams/mimo-v2.6-flash'
    out = run_capture(['opencode', 'models'])
    models = [line.strip() for line in out.splitlines()
              if re.fullmatch(r'[^\s/]+/[^\s]+', line.strip())]
    choices = [Choice(model, model) for model in dict.fromkeys([default, *models])]
    choices.append(Choice('__manual__', 'Andere Modell-ID eingeben ...'))
    model = pick('Modell waehlen', choices)
    if model == '__manual__':
        model = choose('Modell PROVIDER/MODEL (Enter = Abbrechen): ') or None
    return model
