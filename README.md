# Ananta OpenCode Cockpit

**Unified tmux cockpit for OpenCode: side chats, session/model/plan control,
context sync, model routing with failback – mouse and keyboard, no telemetry,
no LLM calls from the tooling itself.**

> Einheitliche Steuerung fuer tmux 3.4 + OpenCode 1.x: Side-Chats, Sessions,
> Modelle, Arbeitsplaene, Kontext-Sync, Router-Status und Logs.
> Keine pip-Abhaengigkeiten. Keine LLM-Aufrufe durch das Cockpit selbst.

## Komponenten

| Modul | Beschreibung | Installationsziel |
|---|---|---|
| `cockpit/` | tmux-Oberflaeche (Menueleiste, CONTROL-Panel, Popups) | `~/.local/share/ananta-cockpit/` + `~/.local/bin/ananta-cockpit` |
| `oc-side/` | Side-Chats als tmux-Popups (Fork der Hauptsitzung) | `~/.local/bin/oc-side` |
| `oc-side-sync/` | Inkrementelle Kontext-Synchronisation Haupt<->Side | `~/.local/bin/oc-side-sync` |
| `slim-router/` | OpenCode-Plugins: Modell-Failback + Context Manager | `~/.config/opencode/plugins/` |
| `slim-router/planctl.py` | Deterministische Arbeitsplan-Verwaltung (`slim-plan`) | `~/.local/bin/slim-plan` |

## Installation

```bash
git clone https://github.com/ananta888/ananta-opencode-cockpit.git
cd ananta-opencode-cockpit
bash install.sh
export PATH="$HOME/.local/bin:$PATH"
```

- Laufzeitdateien liegen nach `~/.local/share/ananta-cockpit/` – unabhaengig
  vom Arbeitsverzeichnis und von Symlinks.
- Jede Installation sichert vorherige Dateien nach
  `~/.local/share/ananta-cockpit/backups/<Zeitstempel>/`.
- Mehrfaches Ausfuehren ist idempotent; **bestehende Configs werden nicht
  ueberschrieben** (nur angelegt, falls abwesend).
- `bash uninstall.sh` entfernt das Projekt wieder; eigene Configs bleiben
  erhalten.

## Start und Stop

```bash
tmux new -s ananta          # falls noch keine tmux-Sitzung
cd ~/ananta && opencode     # OpenCode im linken Bereich
# aus einer Shell (zweites Pane oder nach Verlassen des TUI):
ananta-cockpit start ~/ananta
ananta-cockpit stop
```

- `start` ist idempotent: ein vorhandenes CONTROL-Pane wird erkannt.
- `stop` entfernt das Pane und stellt Statusleiste/Mausbindung wieder her.
- Das CONTROL-Pane wird per Pane-Option `@ananta_cockpit` markiert – auch ohne
  Titel zuverlaessig wiederfindbar.

## Bedienung

Obere Menueleiste (Mausklick) und rechtes Panel (Maus oder Tasten 1–7):

| Taste | Bereich | Inhalt |
|---|---|---|
| 1 | Side-Chat | `o` Fork oeffnen (Modell waehlbar), `c` temporaere Side-Chats aufraeumen |
| 2 | Sessions | `opencode session list` |
| 3 | Modelle | Modelluebersicht (nur Anzeige, keine Umschaltung) |
| 4 | Plaene | `slim-plan brief` |
| 5 | Kontext-Sync | Vorschau -> ausdrueckliche Bestaetigung -> Uebernahme |
| 6 | Router | Konfiguration + Modell-Cooldowns |
| 7 | Logs | Router-/Context-Logs (Auszug) |

Kritische Aktionen (Loeschen, Sync-Uebernahme) fragen ausdruecklich nach.
`q` schliesst das Panel.

## Side-Chats (oc-side)

```bash
oc-side --session ses_XXXX --model xiaomi-token-plan-ams/mimo-v2.6-flash --dir ~/ananta
```

- Oeffnet einen **Fork** der Hauptsitzung in einem tmux-Popup; die Hauptsitzung
  bleibt unveraendert.
- Session-IDs werden gegen `opencode session list` geprueft.
- Erzeugte Forks werden protokolliert (`~/.local/state/ananta-cockpit/side-chats.json`)
  und koennen ueber Menue 1 -> `c` aufgeraeumt werden.

## Kontext-Sync (oc-side-sync)

```bash
oc-side-sync preview --main ses_A --side ses_B --direction main-to-side
oc-side-sync apply   --main ses_A --side ses_B --direction main-to-side --yes
```

- Nur Textnachrichten seit dem letzten Cursor; Tool-Teile und fruehere
  Sync-Markierungen bleiben draussen.
- `apply` ohne `--yes` kontaktiert den Server nicht einmal.
- Uebernahme erfolgt als `noReply`-Notiz (kein LLM-Aufruf); der Ziel-Cursor
  wird vor dem Senden gesperrt (kein doppeltes Uebertragen bei Timeout).

## Modell-Router (slim-router Plugin)

Konfiguration: `~/.config/opencode/slim-router.json`, Zustand:
`<projekt>/.opencode/slim-context/router/`, Log: `/tmp/opencode-slim-router.log`.

- Erkennt Quota-/Rate-Limit-/Netzwerkfehler deterministisch (keine LLM-Aufrufe).
- Respektiert in Fehlermeldungen genannte Reset-Fenster
  ("reset in 2 hours 27 minutes").
- Exponentieller Backoff mit Deckel; Cooldowns ueberleben OpenCode-Neustarts.
- Maximal `max_attempts` Fallbacks pro Sitzung, danach Stopp (keine
  Endlosschleife).
- Erfolgreiche Aufrufe werden nicht unterbrochen; bei Erfolg wird der Zustand
  zurueckgesetzt.
- Wiederherstellung sendet einen **neuen Fortsetzungshinweis**, niemals den
  alten User-Prompt; der Hinweis verlangt zuerst Zustandspruefung.
- Kostenpflichtige Fallbacks laufen nur ueber die in `fallback_models`
  ausdruecklich eingetragenen Modelle – dort entscheidest du, was erlaubt ist.
- **Es werden keine Schluessel protokolliert oder in Projektdateien geschrieben.**

## Tests

```bash
bash tests/run-tests.sh
```

- 33 Python-Tests (unittest): tmux-Start/Idempotenz/Stop, echte tmux-Integration,
  oc-side-Forkerfassung, side-sync Cursor/Duplikatschutz, slim-plan.
- 20 Bun-Tests: Reset-Fenster-Parsing, Fehlerklassifikation, Cooldowns,
  Verhaltenstests gegen einen Mock-Client (keine echten API-Aufrufe).
- 25 Bash-Regressionen: Installation/Idempotenz/Deinstallation in Fake-HOME,
  Klick-Bereiche, Plugin-Export, `plugin:["list"]`-Regression, Geheimnisscan.

**Manuelle Pruefschritte (nicht automatisiert):**

1. In einem echten Terminal: `tmux new -s ananta`, `ananta-cockpit start ~/ananta`.
2. Obere Menueleiste mit der Maus anklicken – jedes Popup muss oeffnen.
3. Side-Chat oeffnen, im Popup arbeiten, Popup verlassen – Hauptsitzung muss
   unveraendert weiterlaufen.
4. Zwei Side-Chats oeffnen, dann Menue 1 -> `c` und einen davon loeschen.
5. Sync zwischen Haupt- und Side-Sitzung: Vorschau pruefen, mit `ja` uebernehmen,
   in der Ziel-Sitzung die Notiz kontrollieren.
6. Router: `/tmp/opencode-slim-router.log` und Router-Menue auf Plausibilitaet
   pruefen (keine wiederholten identischen Fallbacks in Endlosschleife).
7. Fenstergroesse aendern – Panel und Statusleiste muessen bedienbar bleiben.
8. `ananta-cockpit stop` – Layout und Optionen wiederhergestellt.

## Verifiziert / nicht verifiziert

- **Verifiziert im echten Verbund**: `ananta-cockpit start/stop/idempotent` in
  echtem tmux; alle Aktions-CLIs; Sync-Zyklus (init -> Vorschau -> bestaetigte
  Uebernahme -> Duplikatschutz) gegen einen echten `opencode serve`-Server auf
  zwei realen Sitzungen, ohne LLM-Aufruf.
- **Nicht end-to-end getestet**: echte Mausklicks in einem angeklemmten Client
  (benötigt interaktives Terminal), Context-Compaction-Hook mit echtem
  `/compact`, Router-Failback gegen echte Providerfehler ausserhalb der bisher
  beobachteten Faelle, Verhalten bei Terminalgroessenwechsel.

## Bekannte Einschraenkungen

- tmux-Mausbindungen sind serverweit; `MouseDown1Status` wird von diesem Tool
  belegt und bei `stop` nur entfernt, wenn es ihn selbst gesetzt hat.
- Ein tmux-Popup kann ein anderes Pane nicht fernsteuern; Aktionen erfolgen
  ueber eigene CLI-Aufrufe.
- `slim-plan` ist eine reine Zustandsverwaltung; Aufgabenzerlegung geschieht
  durch den Agenten, nicht automatisch.
- Nach Plugin-Aenderungen muss OpenCode neu gestartet werden.
- Oh My OpenAgent wird nicht verwendet und nicht installiert.

## Rollback

- Installation: Backups unter `~/.local/share/ananta-cockpit/backups/<stamp>/`.
- Plugin-Aenderungen: `~/.config/opencode/plugins/*.bak-*` bzw.
  `*.backup-<Zeitstempel>`.
- Konfiguration: bleibt bei `uninstall.sh` erhalten.
- Manuell: `tmux unbind-key -T root MouseDown1Status` entfernt die Mausbindung.

## Lizenz

BSD 3-Clause – siehe [LICENSE](LICENSE).
