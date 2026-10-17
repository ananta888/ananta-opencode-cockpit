"""Shared cockpit actions and their native-menu keyboard routes."""
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Action:
    id: str
    label: str
    key: str
    menu: str


@dataclass(frozen=True, slots=True)
class Menu:
    id: str
    label: str
    key: str
    parent: str


MENUS: Final = {menu.id: menu for menu in (
    Menu('root', 'Ananta', '', ''),
    Menu('project', 'Projekt', 'p', 'root'),
    Menu('chat', 'Chat', 'c', 'root'),
    Menu('context', 'Kontext', 'k', 'root'),
    Menu('view', 'Ansicht', 'a', 'root'),
    Menu('model', 'Modell', 'm', 'root'),
    Menu('tools', 'Werkzeuge', 'w', 'root'),
    Menu('help', 'Hilfe', 'h', 'root'),
    Menu('resize', 'Pane-Groesse', 'r', 'view'),
    Menu('router', 'Router', 'r', 'model'),
    Menu('plans', 'Plaene', 'p', 'tools'),
    Menu('codecompass', 'CodeCompass', 'c', 'tools'),
    Menu('diagnostics', 'Diagnose', 'd', 'tools'),
    Menu('clipboard', 'Zwischenablage', 'z', 'tools'),
)}

ACTIONS: Final = {action.id: action for action in (
    Action('project-switch', 'Projekt wechseln', 'w', 'project'),
    Action('project-new', 'Neues Projekt', 'n', 'project'),
    Action('project-folder', 'Projektordner oeffnen', 'o', 'project'),
    Action('project-recent', 'Letzte Projekte', 'r', 'project'),
    Action('chat-new', 'Neuer Chat', 'n', 'chat'),
    Action('chat-side', 'Neuer Side-Chat', 's', 'chat'),
    Action('chat-resume', 'Chat fortsetzen', 'f', 'chat'),
    Action('chat-rename', 'Chat umbenennen', 'u', 'chat'),
    Action('chat-close', 'Tab schliessen', 'c', 'chat'),
    Action('chat-delete', 'Chat loeschen', 'd', 'chat'),
    Action('chat-list', 'Geoeffnete Chats / Tabs', 'l', 'chat'),
    Action('chat-cleanup', 'Leere Chats aufraeumen', 'x', 'chat'),
    Action('context-to-side', 'Main nach Side senden', 's', 'context'),
    Action('context-to-main', 'Side nach Main senden', 'm', 'context'),
    Action('context-other', 'An anderen Chat senden', 'a', 'context'),
    Action('context-preview', 'Kontextvorschau', 'v', 'context'),
    Action('context-init', 'Kontext initialisieren', 'i', 'context'),
    Action('context-reset', 'Kontext zuruecksetzen', 'r', 'context'),
    Action('context-config', 'Kontext konfigurieren', 'c', 'context'),
    Action('context-snapshots', 'Kontext-Snapshots', 'p', 'context'),
    Action('context-status', 'Sync-Status', 't', 'context'),
    Action('view-left', 'Side links', 'l', 'view'),
    Action('view-below', 'Side unten', 'u', 'view'),
    Action('view-window', 'Side als Fenster', 'w', 'view'),
    Action('view-popup', 'Side als Popup', 'p', 'view'),
    Action('view-zoom', 'Pane maximieren', 'z', 'view'),
    Action('view-sidebar', 'Sidebar ein/aus', 's', 'view'),
    Action('view-next', 'Naechster Tab', 'n', 'view'),
    Action('view-prev', 'Vorheriger Tab', 'v', 'view'),
    Action('view-resize-left', 'Pane nach links vergroessern', 'H', 'resize'),
    Action('view-resize-right', 'Pane nach rechts vergroessern', 'L', 'resize'),
    Action('view-resize-up', 'Pane nach oben vergroessern', 'K', 'resize'),
    Action('view-resize-down', 'Pane nach unten vergroessern', 'J', 'resize'),
    Action('view-sidebar-focus', 'Sidebar fokussieren', 'f', 'view'),
    Action('view-pane-next', 'Naechstes Pane', 'o', 'view'),
    Action('view-copy-mode', 'Scrollen / Copy-Modus', 'c', 'view'),
    Action('view-detach', 'Session verlassen', 'd', 'view'),
    Action('view-window-next', 'Naechstes Fenster', ']', 'view'),
    Action('view-window-prev', 'Vorheriges Fenster', '[', 'view'),
    Action('model-favorite-add', 'Modell als Favorit speichern', 'a', 'model'),
    Action('model-change', 'Modell wechseln', 'w', 'model'),
    Action('model-favorites', 'Modellfavoriten', 'f', 'model'),
    Action('router-toggle', 'Router ein/aus', 't', 'router'),
    Action('router-failback', 'Router-Failback ein/aus', 'f', 'router'),
    Action('router-status', 'Router-Status', 's', 'router'),
    Action('router-config', 'Router konfigurieren', 'k', 'router'),
    Action('plans-open', 'Plaene anzeigen', 'o', 'plans'),
    Action('plans-new', 'Plan anlegen', 'n', 'plans'),
    Action('plans-edit', 'Aufgabe hinzufuegen', 'e', 'plans'),
    Action('plans-validate', 'Naechste Aufgabe', 'v', 'plans'),
    Action('plans-activate', 'Naechste Aufgabe aktivieren', 'a', 'plans'),
    Action('plans-done', 'Aufgabe abschliessen', 'd', 'plans'),
    Action('plans-brief', 'Plan-Briefing', 'b', 'plans'),
    Action('cc-config', 'CodeCompass konfigurieren', 'c', 'codecompass'),
    Action('cc-status', 'CodeCompass-Status', 's', 'codecompass'),
    Action('cc-tools', 'CodeCompass-Werkzeuge', 'w', 'codecompass'),
    Action('cc-start', 'CodeCompass starten', 'a', 'codecompass'),
    Action('cc-login', 'CodeCompass anmelden', 'l', 'codecompass'),
    Action('logs', 'Logs anzeigen', 'l', 'diagnostics'),
    Action('diagnostics', 'Diagnose ausfuehren', 'd', 'diagnostics'),
    Action('cockpit-stop', 'Cockpit beenden', 'q', 'help'),
    Action('help', 'Tasten und Hilfe', 'h', 'help'),
    Action('clipboard-copy', 'Auswahl kopieren', 'c', 'clipboard'),
    Action('clipboard-paste', 'Zwischenablage einfuegen', 'v', 'clipboard'),
)}


def actions_for(menu: str) -> tuple[Action, ...]:
    return tuple(action for action in ACTIONS.values() if action.menu == menu)


def submenus_for(menu: str) -> tuple[Menu, ...]:
    return tuple(child for child in MENUS.values() if child.parent == menu)


def menu_shortcut(menu: str, prefix: str = 'C-b') -> str:
    """Render the route from the user's actual tmux prefix to a menu."""
    keys: list[str] = []
    current = MENUS[menu]
    while current.parent:
        keys.append(current.key)
        current = MENUS[current.parent]
    return ' '.join((prefix, 'g', *reversed(keys)))


def shortcut(action: str, prefix: str = 'C-b') -> str:
    entry = ACTIONS[action]
    return f'{menu_shortcut(entry.menu, prefix)} {entry.key}'
