"""Exercise tool actions against isolated real command/config boundaries."""
import json
import os
import sys
from pathlib import Path

import pytest

# Existing command helpers are standalone modules as well as package files.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'cockpit'))
from cockpit import tool_actions as actions


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv('OC_CONFIG_DIR', str(tmp_path / 'config'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))
    return tmp_path


def test_router_toggles_preserve_unrelated_config(sandbox):
    # Given an existing configuration with unrelated settings.
    path = sandbox / 'config/slim-router.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'enabled': True, 'failback_enabled': False, 'model': 'keep/me'}))
    # When both toggles are executed.
    actions.execute('router-toggle', str(sandbox))
    actions.execute('router-failback', str(sandbox))
    # Then only the requested flags change.
    assert json.loads(path.read_text()) == {'enabled': False, 'failback_enabled': True, 'model': 'keep/me'}
    print('ROUTER_CONFIG=' + path.read_text())


def test_plan_workflow_writes_real_plan_records(sandbox, monkeypatch):
    # Given user answers for a new plan and task.
    answers = iter(['Objective', 'Task title', 'Task description', '001', 'pytest passed'])
    monkeypatch.setattr(actions, 'choose', lambda prompt: next(answers))
    # When the public actions drive the real slim-plan lifecycle.
    for action in ('plans-new', 'plans-edit', 'plans-open', 'plans-validate', 'plans-activate', 'plans-brief', 'plans-done'):
        assert actions.execute(action, str(sandbox))
    # Then the task is completed with evidence and no active task remains.
    root = sandbox / '.opencode/slim-context'
    task = json.loads((root / 'plans/001.json').read_text())
    assert task['status'] == 'done'
    assert task['evidence'] == ['pytest passed']
    assert json.loads((root / 'state.json').read_text())['current_task'] is None
    print('PLAN_RECORD=' + json.dumps(task))


def test_editor_supports_arguments_and_spaces(sandbox, monkeypatch):
    # Given an editor command containing arguments and a spaced filename.
    script = sandbox / 'fake editor.py'
    output = sandbox / 'editor-args.json'
    script.write_text('import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))')
    import shlex
    monkeypatch.setenv('EDITOR', shlex.join([sys.executable, str(script), str(output), '--wait']))
    monkeypatch.delenv('VISUAL', raising=False)
    # When the configuration action launches the editor.
    actions.execute('context-config', str(sandbox))
    # Then arguments retain their boundaries.
    assert json.loads(output.read_text()) == ['--wait', str(sandbox / 'config/slim-context.json')]
    print('EDITOR_ARGS=' + output.read_text())


def test_codecompass_failure_is_visible(sandbox, monkeypatch):
    # Given a real executable that reports a nonzero status.
    binary = sandbox / 'oc-codecompass'
    binary.write_text('#!/bin/sh\nexit 7\n')
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', f'{sandbox}:{os.environ["PATH"]}')
    # When CodeCompass status fails.
    with pytest.raises(actions.ToolActionError, match='Exit 7'):
        actions.execute('cc-status', str(sandbox))
    # Then the action cannot be mistaken for success.
    print('ERROR_OBSERVABLE=ToolActionError Exit 7')


def test_diagnostics_does_not_print_credentials(sandbox, capsys):
    # Given secret-bearing adjacent configuration and token files.
    config = sandbox / 'config'
    config.mkdir()
    (config / 'slim-router.json').write_text('{"token":"SECRET"}')
    state = sandbox / 'state/ananta-cockpit'
    state.mkdir(parents=True)
    (state / 'codecompass-token.json').write_text('{"token":"SECRET"}')
    # When diagnostics and logs are requested.
    actions.execute('diagnostics', str(sandbox))
    actions.execute('logs', str(sandbox))
    # Then only paths and status are displayed.
    captured = capsys.readouterr().out
    assert 'SECRET' not in captured
    assert 'codecompass-token.json' not in captured
    print('DIAGNOSTICS_OUTPUT=' + repr(captured))
