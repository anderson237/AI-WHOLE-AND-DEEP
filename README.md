# AI-WHOLE-AND-DEEP

Tri-union d'agents pilotee par un cerveau cloud partage :
**OpenClaw** (Directeur general) + **Hermes Agent** (Chef de projet) + **opencode** (Ingenieur dev).

Tous les agents consomment un relais local unique OpenAI-compatible qui sert le modele
`deepseek-v4-flash-free` (provider `opencode`, cloud) via opencode serve. Aucune inference locale.

## Architecture

```
OpenClaw ─┐                 ┌─ opencode serve :4096 (outils OFF)
Hermes ───┼─ bridge.py :5050 ─┤
opencode ─┘                 └─ deepseek-v4-flash-free (cloud)
```

- `hermes-brain/bridge.py` — relais OpenAI-compatible : decisions + `tool_calls` JSON
  (multiples, streamables), pool de sessions prechauffees (temps morts ~2-3s), vision
  (images -> file parts), `Connection: close` sur SSE, reponses sans raisonnement interne.
- `hermes-brain/start_brain.bat` — demarre opencode serve + pont + verification sante.
- `hermes-brain/config.hermes.example.yaml` — config Hermes branchee au pont.
- `hermes-brain/openclaw.example.json` — config OpenClaw (provider `brain` -> :5050,
  gateway local chaude sur 18789, canal Telegram via env `TELEGRAM_BOT_TOKEN`).
- `hermes-brain/requirements.txt` — dependances (module standard uniquement).
- `SYSTEM_EVOLUTIONS.md` — journal des evolutions + exigences fonctionnelles (a mettre a jour
  a chaque changement fonctionnel, puis push).

## Demarrage

```powershell
hermes-brain\start_brain.bat
Invoke-RestMethod http://127.0.0.1:5050/health   # -> { ok: true, warm_sessions: N }
```

## Exemple de chat

```powershell
python -c "import json,urllib.request; b=json.dumps({'model':'deepseek-v4-flash-free','messages':[{'role':'user','content':'dis OK'}]}).encode(); r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5050/v1/chat/completions',b,{'Content-Type':'application/json'})); print(json.load(r)['choices'][0]['message']['content'])"
```

## Repo de travail local

Le dossier source synchronise sur GitHub :
`C:\Users\<USER>\Downloads\AI-WHOLE-AND-DEEP`
(copie de reference du systeme fonctionnel, mise a jour et poussee regulierement).

## Rôles

| Agent    | Role                  | Canaux principaux       |
|----------|-----------------------|--------------------------|
| OpenClaw | Directeur general     | WhatsApp, Telegram, UI   |
| Hermes   | Chef de projet logiciel | CLI, strategy, web     |
| opencode | Ingenieur dev + cerveau | Code + raisonnement cloud |
