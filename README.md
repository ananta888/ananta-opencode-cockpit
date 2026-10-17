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
| `oc-codecompass/` | Ananta-Hub-MCP (CodeCompass) an OpenCode anbinden | `~/.local/bin/oc-codecompass` |

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

Alles-in-einem (empfohlen): tmux-Session + Cockpit-Statusleiste/Sidebar +
OpenCode mit CodeCompass-MCP und den eigenen OpenCode-Plugins:

```bash
ananta-cockpit up ~/ananta                 # Session wird angelegt/betreten
ananta-cockpit up ~/ananta -m prov/modell  # mit Modell-Vorauswahl
ananta-cockpit up ~/ananta --detach        # Hintergrund (tmux attach -t <name>)
ananta-cockpit up ~/ananta --no-mcp        # ohne Hub-MCP
ananta-cockpit up ~/ananta --dry-run       # nur anzeigen, nichts ausfuehren
```

- Session-Name = Projektname (`-s NAME` zum Ueberschreiben); idempotent:
  ein erneuter Aufruf betritt die laufende Session.
- Fehlt ein Hub-Token, wird der interaktive Login angeboten; ohne gueltiges
  Token startet OpenCode trotzdem (ohne MCP, mit Hinweis).
- Nach dem Verlassen von OpenCode bleibt eine Shell in der Session aktiv.

Manuell (Cockpit ohne OpenCode-Start):

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

Oben eine **Menueleiste** (`ananta  Chat  Kontext  Ansicht  Modell  Werkzeuge  Hilfe`)
mit Untermenues per Mausklick oder `Prefix g` + Menuebuchstabe; daneben **Chat-Tabs**
in der Statusleiste (Klick fokussiert, Rechtsklick oeffnet das Chat-Menue,
`Prefix g 1–9` wechselt den Chat). Rechts steht das **Chat-Baum-Panel**:

| Taste | Wirkung |
|---|---|
| Pfeil auf/ab, Klick | Chat auswaehlen |
| Enter/Klick | geoeffneten Chat fokussieren; gespeicherten fortsetzen |
| `n` | neuer Hauptchat |
| `s` | neuer Side-Chat (Fork des aktiven Chats) |
| `m` | Hauptmenue oeffnen |
| Rechtsklick | Chat-Menue (umbenennen, schliessen, Ansicht, Sync ...) |
| `q` | Panel ausblenden (`Ansicht -> Sidebar ein/aus` holt es zurueck) |

Alle Funktionen des Cockpits sind auch ohne Maus ueber die Menues erreichbar;
jeder Menueeintrag zeigt seine Tastenkombination (`Prefix g` + Route) an.

Kritische Aktionen (Loeschen, Sync-Uebernahme) fragen ausdruecklich nach.

Auswahllisten in den Popups lassen sich mit **Pfeil auf/ab + Enter** oder
**Mausklick** bedienen. Einfach tippen filtert nach Titel, Session-ID oder Modell;
Backspace loescht den Filter. Mausrad und Bild auf/ab scrollen, Pos1/Ende springen
zum ersten/letzten Treffer. **Esc** bricht ab.
**Rechtsklick** auf einen Eintrag oder **F2** kopiert dessen Session-ID bzw.
Modell-ID in die Systemzwischenablage, ohne die Auswahl zu bestaetigen.
Unter WSL verwendet das Cockpit dafuer die Windows-Zwischenablage (`clip.exe`).
Fuer beliebigen Text im Windows Terminal: **Shift gedrueckt halten und mit der
Maus ziehen**, dann **Ctrl+Shift+C** zum Kopieren bzw. **Ctrl+Shift+V** zum Einfuegen.
Beim Aufraeumen lassen sich mehrere Side-Chats mit Leertaste oder Klick markieren
und mit Enter uebernehmen; vor dem Loeschen folgt eine separate Bestaetigung.
Session-IDs muessen nicht mehr abgetippt werden. Ohne interaktives Terminal gibt
es eine nummerierte Auswahl.

## Side-Chats (oc-side)

```bash
oc-side --session ses_XXXX --model xiaomi-token-plan-ams/mimo-v2.6-flash --dir ~/ananta
oc-side --session ses_SIDE_ID --resume --layout left --dir ~/ananta
oc-side --session ses_SIDE_ID --resume --layout below --dir ~/ananta
```

- Oeffnet einen **Fork** der Hauptsitzung in einem tmux-Popup; die Hauptsitzung
  bleibt unveraendert.
- Aus dem Cockpit startet der Fork im bereits offenen Popup (`--inline`),
  da tmux keine verschachtelten Popups ausfuehrt. Startfehler bleiben sichtbar.
- Im Menue **Side-Chat -> Bestehenden Side-Chat fortsetzen** eine gespeicherte
  Sitzung waehlen. Dabei entsteht kein weiterer Fork; das bisherige Modell bleibt
  erhalten. Erfasste Side-Chats stehen zuerst; weitere OpenCode-Sitzungen folgen,
  damit auch Chats aus direkt geschlossenen tmux-Panes wieder erreichbar bleiben.
- Beim Oeffnen und Fortsetzen ist die **Platzierung** waehlbar: Popup, links neben
  der Hauptsitzung oder darunter. Pane-Starts schliessen das Auswahl-Popup sofort.
  Die Cockpit-Seitenleiste bleibt dabei erhalten.
- Zum Wechsel der Darstellung den Chat beenden und dieselbe Sitzung erneut mit
  der gewuenschten Platzierung fortsetzen. Schliessen loescht die Sitzung nicht.
  Zwischen eingebetteten Panes mit **Ctrl+B, Pfeiltaste** wechseln; die Pane-Groesse
  laesst sich wie gewohnt mit tmux veraendern.
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

## CodeCompass ueber den Ananta-Hub (oc-codecompass)

```bash
oc-codecompass login        # Hub-Login; Token+Refresh landen 0600 im State-Dir
oc-codecompass status       # Exposure/Tool-Anzahl des /v1/mcp-Endpunkts
oc-codecompass tools        # alle ueber MCP sichtbaren Tools
oc-codecompass mcp-config   # OpenCode-MCP-Konfiguration als JSON
oc-codecompass run --       # OpenCode mit injiziertem MCP-Server starten
oc-side --codecompass ...   # Side-Chat gleich mit CodeCompass
```

- Der Hub stellt `/v1/mcp` als MCP-Endpunkt (JSON-RPC: initialize, ping,
  tools/list, tools/call, resources). OpenCode verbindet sich als
  `remote`-Server mit Bearer-Token.
- Konfiguration: `~/.config/ananta-cockpit/codecompass.json`
  (`hub_url` – nur 127.0.0.1/localhost zulaessig, `server_name`).
- Access-Token (1 h) wird per rotierendem Refresh-Token automatisch erneuert.
- **Voraussetzungen auf Hub-Seite** (Ananta-Projekt):
  `exposure_policy.mcp.enabled=true` (plus `allow_user_auth`), und der
  `/v1/mcp`-Handler muss den MCP-Handshake (`initialize`/`ping`/202 fuer
  Notifications) beherrschen und **keine zusaetzlichen Felder wie `trace_id`
  in JSON-RPC-Antworten** senden – sonst bricht OpenCodes StreamableHTTP-Client
  ab und faellt auf SSE zurueck.
- Sichtbare Tools richten sich nach der Operation-Policy des Hubs
  (z. B. `codecompass.retrieve`, `architecture_overview`, `layers_plan`).

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

- 41 Python-Tests (unittest): tmux-Start/Idempotenz/Stop, echte tmux-Integration,
  oc-codecompass (Mock-Hub), oc-side-Forkerfassung, side-sync Cursor/
  Duplikatschutz, slim-plan.
- 23 Bun-Tests: Reset-Fenster-Parsing, Fehlerklassifikation, Cooldowns,
  Verhaltenstests gegen einen Mock-Client, Loader-Vertrag der benannten
  Exporte (keine echten API-Aufrufe).
- 68 Bash-Regressionen: Installation/Idempotenz/Deinstallation in Fake-HOME,
  Klick-Bereiche, Plugin-Export, `plugin:["list"]`-Regression, Geheimnisscan
  (test_install.sh) sowie `up`-Argumente/Dry-Run/echtes tmux-E2E mit Stubs
  (test_up.sh).

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
9. `oc-codecompass login/status/tools` gegen den laufenden Hub.
10. `oc-codecompass run -- mcp list` – der Server `ananta_codecompass` muss
    `connected` zeigen.
11. Menue 7 (CodeCompass) -> `t`: Tool-Liste erscheint.
12. `ananta-cockpit up <projekt>` in einem echten Terminal: Session, Sidebar,
    Statusleiste und OpenCode muessen zusammenkommen; `--dry-run` vorher
    gegenlesen.

## Verifiziert / nicht verifiziert

- **Verifiziert im echten Verbund**: `ananta-cockpit start/stop/idempotent` in
  echtem tmux; alle Aktions-CLIs; Sync-Zyklus (init -> Vorschau -> bestaetigte
  Uebernahme -> Duplikatschutz) gegen einen echten `opencode serve`-Server auf
  zwei realen Sitzungen, ohne LLM-Aufruf; CodeCompass-Anbindung gegen den
  laufenden Ananta-Hub: `opencode mcp list` = connected und ein echter
  `tools/call` auf `codecompass.retrieve` liefert Retrieval-Ergebnisse
  (Budget-/Dedup-Diagnostik), ohne LLM-Aufruf; **Alles-in-einem-Start
  `ananta-cockpit up`**: echte tmux-Session mit Sidebar/Statusleiste, das
  laufende OpenCode-TUI traegt die MCP-Injection (`ananta_codecompass` +
  Bearer im Prozess-Env, TUI zeigt "3 MCP"), `slim-router`/`context-manager`
  laden fehlerfrei (OpenCode-Loader-Vertrag getestet); Plugin-Ladefehler
  (`failed to load plugin`/`config hook failed`) sind behoben.
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
