import os
import shutil
import subprocess


def copy_text(text: str) -> bool:
    """Schreibt Text in die Systemzwischenablage; False bei fehlendem Zugriff."""
    commands = [('clip.exe', [], 'utf-16le'), ('pbcopy', [], 'utf-8')]
    if os.environ.get('WAYLAND_DISPLAY'):
        commands.append(('wl-copy', [], 'utf-8'))
    if os.environ.get('DISPLAY'):
        commands.append(('xclip', ['-selection', 'clipboard'], 'utf-8'))
    for name, args, encoding in commands:
        executable = shutil.which(name)
        if not executable:
            continue
        try:
            result = subprocess.run([executable, *args], input=text.encode(encoding),
                                    capture_output=True, timeout=3, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return True
    return False
