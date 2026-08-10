# SYSTEM EVOLUTIONS & REQUIREMENTS — AI-WHOLE-AND-DEEP

Journal vivant de l'evolution du systeme "tri-union" :
**OpenClaw (DG / controle) + Hermes Agent (chef de projet) + opencode (ingenieur dev)**
tous alimentes par un pont local unique qui sert le modele cloud partage `deepseek-v4-flash-free`.

Mise a jour a chaque changement fonctionnel, puis push sur GitHub.

---

## OBJECTIF GLOBAL

Construire et maintenir une triade d'agents :
- **OpenClaw** = Directeur general (canaux UI : WhatsApp, Telegram, Discord...).
- **Hermes Agent** = Chef de projet logiciel (strategie, web, outils).
- **opencode** = Ingenieur dev (code) — sert AUSSI de "cerveau cloud" partage.

Chacun consomme `http://127.0.0.1:5050/v1` (OpenAI-compatible) via `bridge.py`.
opencode ne voit AUCUN outil (tous desactives) : il ne renvoie que des `tool_calls`
JSON que OpenClaw/Hermes executent eux-memes.

---

## ARCHITECTURE

```
OpenClaw ─┐                 ┌─ opencode serve :4096 (outils OFF)
Hermes ───┼─ bridge.py :5050 ─┤
opencode ─┘                 └─ deepseek-v4-flash-free (cloud, provider opencode)
```

- **bridge.py** : expose une API OpenAI-compatible (`/v1/chat/completions`,
  `/v1/embeddings`, `/v1/models`, `/health`). Convertit l'appel OpenAI en message
  opencode (parties text/file), renvoie texte OU `tool_calls` OpenAI standards.
- Vision : les `image_url` sont projetees en `FilePartInput` (`{"type":"file","mime","url"}`).
- Le pont maintient un **pool de sessions opencode prechauffees** pour eliminer le cold start.

---

## VERSIONNEL / EVOLUTIONS

### v7 — CANAL TELEGRAM + OUTILS VIDEOS (11/08/2026)
- **Canal Telegram active** : bot `@WholeAndDeepBot` (token via @BotFather, stocke en
  variable d'environnement utilisateur `TELEGRAM_BOT_TOKEN`, jamais en clair dans la
  config). Config `channels.telegram` : `enabled`, `botToken` (env), `dmPolicy`,
  `groups`. Le canal ne se connecte PAS via `openclaw channels login` : polling HTTP.
- **yt-dlp installe** (vehicule la transcription vidéo). Executable deja dans le
  PATH : `C:\Python314\Scripts\` refuse l'ecriture sans admin -> on utilise le venv
  Hermes (`AppData\Local\hermes\hermes-agent\venv\Scripts`) deja dans le PATH session
  et le Scripts dir user `AppData\Roaming\Python\Python314\Scripts` ajoute au PATH.
- Verification chaine complete : pont renvoie `tool_calls` -> OpenClaw execute bash
  -> resultat re-injecte -> reponse finale. OK.

### v6 — FIX REPONSES PROPRES + TOOL_CALLS MULTIPLES (11/08/2026)
- **Bug majeur** : les reponses Telegram contenaient tout le raisonnement du modele
  ("The user sent Salut... I should respond...") avant la vraie reponse. Cause :
  `run_turn` concatenait les parts `text` ET `reasoning` d'opencode.
- Fix : ne renvoyer que le `text` (fallback `reasoning` si pas de texte).
- **Bug 2** : `parse_model_reply` echouait sur PLUSIEURS `tool_calls` JSON paralleles
  (il prenait du 1er `{` au dernier `}` -> JSON invalide -> retombe en texte brut,
  envoyant tout le raisonnement + JSON sur le canal).
- Fix : `extract_tool_calls()` avec `json.JSONDecoder().raw_decode` itere sur tous les
  objets JSON ; le pont emet maintenant des `tool_calls` multiples en streaming SSE
  standard (un chunk par appel avec `index`). OpenClaw execute chaque appel.
- Verifie : streaming texte propre + streaming multi tool_calls OK.

### v5 — GATEWAY OPENCLAW CHAUDE (10/08/2026)
- **Bootstrap reduit** : demarrage de la gateway OpenClaw en arriere-plan
  (`openclaw gateway run`, mode local, port 18789, auth par token) au lieu d'un
  process embedded `--local` a chaque appel.
- La gateway prechauffe les plugins (~1s) et garde le runtime d'agent vivant.
  Resultat : tour agent **~75s (embedded) -> ~42s (gateway)**.
- Le fetch modele via le pont ne prend que ~2.7-8.7s ; le reste est l'assemblage
  du system prompt OpenClaw (31k chars dont ~29.8k de schemas d'outils) + contexte.

### v4 — FIX CONNECTION CLOSE SSE (10/08/2026)
- **Bug majeur corrige** : les reponses SSE (`text/event-stream`) n'envoyaient pas
  `Connection: close`. OpenClaw (Node fetch, HTTP/1.1 keep-alive) attendait la
  fermeture de connexion (EOF) pour finaliser le tour -> **~38 min bloques** apres
  la reponse modele (le pont repondait pourtant en ~3s).
- Fix : `Connection: close` ajoute aux reponses stream (texte ET tool_calls).
  Resultat : tour OpenClaw complet **~38 min -> ~75s** (dont ~32s de bootstrap
  fixe du runtime embedded OpenClaw, hors pont).

### v3 — OPTIMISATION TEMPS MORTS (10/08/2026)
- **Pool de sessions prechauffees** : opencode paie ~30s de bootstrap a la 1re requete
  d'une session. Le pont prime un pool (`BRIDGE_POOL`, defaut 4) de sessions rechauffees
  ("ok") ; le 1er message reel d'une conversation passe en session chaude.
  Resultat : temps de reponse **30s -> ~2.3s**.
- **Seed supprime** : l'ancien code renvoyait l'historique a opencode dans un message
  intermediaire (round-trip complet en plus). Le prompt PROTOCOL (`%HISTORY%`) suffit.
- **Streaming sans throttle** : plus de sleep(0.015) par chunk (`BRIDGE_STREAM_MS`, defaut 0).
- **Refill en arriere-plan** : un thread recharge le pool automatiquement.
- Endpoint `/health` ajoute (etat + `warm_sessions` + `conversations`).
- Variables d'env : `BRIDGE_PORT` (5050), `BRIDGE_POOL` (4), `BRIDGE_STREAM_MS` (0).

### v2 — RELAIS D'OUTILS (historique)
- Routine decisionnelle : prompt PROTOCOL `%TOOLS%` / `%HISTORY%` / `%USER%`.
- Parse JSON `{"name","arguments"}` -> `tool_calls` OpenAI standards.
- Carte des images vers `FilePartInput`.
- Streaming SSE compatible OpenAI (chat completions).

### v1 — PONT OpenAI-COMPATIBLE (historique)
- Premier pont testant la reponse `OK` via une API OpenAI-compatible.

---

## REQUIREMENTS (exigences fonctionnelles)

### RF1 — Un point d'entree unique
- Les 3 agents doivent pouvoir utiliser `http://127.0.0.1:5050/v1` sans config specifique
  (compatible OpenAI : `/chat/completions`, `/embeddings`, `/models`).

### RF2 — Decision seule, execution par l'appelant
- opencode ne doit PAS executer d'outil : mode `ALL_TOOLS_OFF`.
- Il doit renvoyer, quand necessaire, un `tool_calls` JSON valide
  (`{"name": <fn>, "arguments": {...}}`) que le client execute.

### RF3 — Temps morts minimaux
- Cold start opencode elimine par pool de sessions prechauffees.
- Cible : reponse en <= ~3s en session chaude.

### RF4 — Vision (images)
- Les `image_url` (OpenAI) ou parties `file` (opencode) doivent transiter correctement.

### RF5 — Session continue
- Le pont conserve un mapping conversation -> session opencode (fingerprint).
- Historique encode en texte (`SYSTEM:`/`USER:`/`ASSISTANT:`/`TOOL RESULT:`).

### RF6 — Securite / vie privee
- Aucun secret en clair dans le repo : configs d'exemple avec valeurs factices
  (`sk-local`, `baseUrl` localhost).
- Le pont reste en loopback (`127.0.0.1`) par defaut.

### RF7 — Redemarrage simple
- `start_brain.bat` : verifie/demarre opencode serve (4096) + pont (5050), test health.

---

## PROCEDURE DE TEST RAPIDE

```powershell
# 1) Lancer le systeme
C:\Users\<USER>\Downloads\AI-WHOLE-AND-DEEP\hermes-brain\start_brain.bat

# 2) Verifier la sante
Invoke-RestMethod http://127.0.0.1:5050/health

# 3) Chat direct (non stream)
python -c "import json,urllib.request; b=json.dumps({'model':'deepseek-v4-flash-free','messages':[{'role':'user','content':'dis OK'}]}).encode(); r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5050/v1/chat/completions',b,{'Content-Type':'application/json'})); print(json.load(r)['choices'][0]['message']['content'])"

# 4) Test OpenClaw (session dediee)
openclaw agent --local --session-key agent:main:smoke -m "Reply with exactly: OK"
```

---

## BILAN DE PERFORMANCE (10/08/2026)

| Etape                              | v2 (avant)  | v3 (apres)  |
|------------------------------------|-------------|-------------|
| opencode 1er message (session froide) | ~29.8s    | ~2.4s (pool)|
| bridge /v1/chat/completions          | ~5.9s      | ~2.3s       |
| stream chunk sleep                  | 15ms/chunk  | 0 (defaut)  |
| tour agent OpenClaw complet          | ~38 min (blocage EOF SSE) | ~75s (fix v4) |
| tour agent via gateway chaude        | -                          | ~42s (v5)     |
| reponse Telegram propre (sans raisonnement) | -                 | v6          |
| tool_calls paralleles executes      | -                          | v6 (multi)   |
| canal Telegram actif (bot @WholeAndDeepBot) | -               | v7          |

Note : le fetch modele via le pont est ~3s. Le reste (~35s) est l'assemblage du
system prompt OpenClaw (31k chars, dont ~29.8k de schemas d'outils) + gestion de
contexte. Reduire les outils/skills charges reduirait encore ce temps.
Le runtime embedded d'OpenClaw ajoute aussi son propre overhead fixe (plugins,
bootstrap) hors du controle du pont.

---

## NOTES DE SESSION — TELEGRAM (11/08/2026)

- Demarrage : config `channels.telegram` sans token en clair -> la gateway refuse de
  demarrer (`SecretRefResolutionError: TELEGRAM_BOT_TOKEN missing`). Resolution :
  variable d'environnement persistante scope User, puis relance du gateway avec
  `$env:TELEGRAM_BOT_TOKEN` repasse dans la meme session shell.
- La gateway peut relancer un `config restart` automatique a la detection d'un
  changement de config (`config change detected; evaluating reload`) ; si un secret
  env manque dans cette sous-session, ce restart echoue. Toujours demarrer la gateway
  avec la variable d'env dans le scope courant.
- `openclaw channels status` : « Telegram default: enabled, configured, running,
  connected, mode:polling ».
- Compaction : `agents.defaults.compaction` mis a jour pour les longues sessions
  (`mode: safeguard`, `reserveTokensFloor: 24000`, `keepRecentTokens: 50000`,
  `maxHistoryShare: 0.7`, `recentTurnsPreserve: 3`).
