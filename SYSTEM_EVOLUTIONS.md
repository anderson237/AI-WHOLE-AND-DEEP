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

Note : l'agent runtime embedded d'OpenClaw ajoute son propre overhead fixe
(plugins, bootstrap) hors du controle du pont.
