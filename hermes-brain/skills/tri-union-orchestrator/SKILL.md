---
name: tri-union-orchestrator
description: Orchestrateur de la triade AI-WHOLE-AND-DEEP (OpenClaw DG + Hermes chef de projet + opencode cerveau). Use when controlling ClawHub skills, Hermes Skills Hub, OpenClaw plugins/Telegram, or routing work between the three agents with <5s latency on native tools.
---

# Tri-Union Orchestrator (AI-WHOLE-AND-DEEP)

opencode est le cerveau/orchestrateur. Il pilote OpenClaw (canaux) et Hermes
(arsenal d'outils/skills) SANS attendre leurs tours d'agent : les outils natifs
opencode (bash, read, write, edit, webfetch, websearch, task) sont instantanes.
Le modele cloud (`deepseek-v4-flash-free` via bridge :5050 -> opencode serve
:4096) ne sert QUE le raisonnement, jamais l'execution.

## Regle de latence (< 5s)

- TOUT ce qui est local passe par les outils natifs opencode (bash/files/web) :
  ~0-200ms, jamais par un tour d'agent OpenClaw/Hermes (40s+).
- N'appeler le modele (chat) que pour la decision/redaction, jamais pour executer.
- Pool bridge : 4 sessions chaudes -> 1er tour ~12s (modele cloud), les
  suivants reutilisent la session. Preferer plusieurs outils natifs a un seul
  tour de raisonnement long.

## Hermes Skills Hub (ClawHub + registres)

Hub : 90k+ skills depuis official / github / clawhub / lobehub / skills-sh /
nvidia / openai / anthropic / huggingface / voltagent / gstack / minimax.

- Chercher : `hermes skills search <query>` (flag `--source clawhub`, `--json`)
- Parcourir : `hermes skills browse`
- Previsualiser : `hermes skills inspect <identifier>`
- Installer : `hermes skills install <identifier>`
- Lister installes : `hermes skills list`
- Creer/publier un skill : `hermes skills publish` (apres creation du dossier)
- Gestion des taps : `hermes skills tap list`

Les skills installes tombent dans `AppData\Local\hermes\skills\<cat>\
<skill>\SKILL.md`, qui est DEJA branche dans opencode via `skills.paths`.
Donc apres `hermes skills install`, le skill est utilisable dans opencode au
prochain redemarrage, execute avec les outils natifs.

## OpenClaw (DG / canaux)

- CLI : `openclaw <cmd>` (gateway locale :18789, token `openclaw-local-trio`).
- MCP expose a opencode : conversations/messages/evenements/permissions (pas les
  plugins). Les plugins OpenClaw (browser, canvas, document-extract...) sont
  pilotes via la CLI OpenClaw ou en bash direct.
- Telegram : bot `@WholeAndDeepBot` (env `TELEGRAM_BOT_TOKEN`), dmPolicy
  allowlist, owner `telegram:8534369207`.
- Redemarrage gateway (Windows) : injecter `$env:TELEGRAM_BOT_TOKEN`, puis
  `Start-Process openclaw.cmd gateway run`. Toujours valider :
  `openclaw config validate` apres edit JSON.
- Session ACP liee : `agent:opencode:acp:...` (persistant, acpx). Le prompt
  envoye a cette session est patche (v10) pour prefixer le contenu cite des
  replies Telegram. Reappliquer apres maj npm :
  `python hermes-brain\reapply_acp_reply_patch.py`.

## Hermes (atelier d'outils)

- CLI : `hermes <cmd>` (venv `AppData\Local\hermes\hermes-agent`).
- MCP expose a opencode : messagerie + permissions uniquement. Les outils riches
  Hermes (web_tools, file_tools, skills_tool, terminal, cron...) ne sont PAS
  exposes via MCP : les exécuter via CLI (`hermes chat -q "..." -Q`) ou, mieux,
  reprendre leur logique avec les outils natifs opencode (webfetch/bash/read).
- Gateway Hermes : `hermes gateway run --accept-hooks` (bot
  `@whole_and_deep_hermes_bot`).
- Skills Hermes executes nativement par opencode : voir section Hub.

## Workflow type (symbiose)

1. `hermes skills search <query>` -> identifier (bash natif, ~1s).
2. `hermes skills install <identifier>` (si pas deja la).
3. Lire `...\<skill>\SKILL.md` (read natif) et appliquer avec les outils natifs.
4. Envoyer le resultat sur Telegram via MCP `openclaw_messages_send` ou
   `hermes_messages_send`.

## References fichier

- Config opencode : `~\.config\opencode\opencode.json`
- Repo : `C:\Users\HP ELITEBOOK G3\Downloads\AI-WHOLE-AND-DEEP`
- Bridge : `...\hermes-brain\bridge.py` (pool, tool_calls, streaming)
- Journal evolutions : `SYSTEM_EVOLUTIONS.md` (a mettre a jour a chaque
  changement fonctionnel puis push).
