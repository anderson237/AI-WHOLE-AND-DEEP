# -*- coding: utf-8 -*-
"""
HERMES BRAIN BRIDGE v3 - Relay complet d'outils (optimise temps morts)

Objectif : quasi zero temps mort entre un appel OpenAI-compatible et la reponse.

Optimisations v3 :
  1) POOL DE SESSIONS PRECHAUFFEES : opencode serve paie ~30s de bootstrap
     a la PREMIERE requete d'une session. On maintient un pool de sessions
     deja rechauffees ("ok") pour que le 1er message reel d'une conversation
     soit traite en session chaude (~2-5s au lieu de ~30s).
  2) SEED SUPPRIME : l'ancien code renvoyait l'historique a opencode dans un
     message intermediaire (1 aller-retour complet). Le prompt PROTOCOL
     (%HISTORY%) suffit deja -> round-trip en moins.
  3) STREAMING SANS THROTTLE : plus de sleep(0.015) par chunk.
  4) REFILL EN ARRIERE-PLAN : le pool se recharge automatiquement.

Architecture : OpenClaw/Hermes -> :5050 (ce relais) -> opencode :4096 -> cloud.
opencode tourne SANS outils (ALL_TOOLS_OFF) et ne renvoie que des tool_calls
JSON que OpenClaw/Hermes executent eux-memes.
"""
import json
import os
import re
import time
import threading
import uuid
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPCODE = "http://127.0.0.1:4096"
MODEL_ID = "deepseek-v4-flash-free"
PROVIDER = "opencode"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("BRIDGE_PORT", "5050"))

NO_TOOLS = ['invalid', 'question', 'bash', 'read', 'glob', 'grep', 'edit', 'write',
            'task', 'webfetch', 'todowrite', 'websearch', 'skill', 'apply_patch']
ALL_TOOLS_OFF = {t: False for t in NO_TOOLS}
DEFAULT_MODEL = {"id": MODEL_ID, "providerID": PROVIDER, "modelID": MODEL_ID}

WARMUP_TEXT = "Acknowledge this warmup with a single word and wait for your next instruction."
POOL_SIZE = int(os.environ.get("BRIDGE_POOL", "4"))
STREAM_CHUNK_MS = float(os.environ.get("BRIDGE_STREAM_MS", "0"))

_lock = threading.Lock()
_convs = {}
_MAX_CONVS = 400

_pool = []
_pool_lock = threading.Lock()

PROTOCOL = """You are the reasoning engine of the agent Hermes, which runs on the user's machine.
Hermes executes FUNCTIONS for you. You do not have any tools yourself and you must not pretend otherwise.

AVAILABLE FUNCTIONS (JSON Schema):
%TOOLS%

RULES:
- If the request can be answered directly, or no function is needed, reply naturally as the assistant (plain text, no JSON).
- If a function IS needed, reply with EXACTLY ONE JSON object and nothing else (no markdown fences, no commentary):
  {"name": "<function name>", "arguments": { ... fields matching the schema ... }}
- Never invent function names: use only the ones above.
- Never fabricate function results.
- Continue working step by step: after a TOOL RESULT, decide if another function is needed or give the final reply.

PAST CONVERSATION:
%HISTORY%

CURRENT USER TURN:
%USER%
"""


def oc_post(path, body, timeout=2400):
    req = urllib.request.Request(OPCODE + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def oc_create_session():
    return oc_post("/session", {"title": "hermes-brain"})["id"]


def oc_warm(sid):
    oc_post(f"/session/{sid}/message",
            {"parts": [{"type": "text", "text": WARMUP_TEXT}],
             "model": DEFAULT_MODEL, "tools": ALL_TOOLS_OFF}, timeout=300)


def pool_get():
    with _pool_lock:
        if _pool:
            return _pool.pop()
    sid = oc_create_session()
    return sid


def pool_refill_loop():
    while True:
        try:
            with _pool_lock:
                need = POOL_SIZE - len(_pool)
            if need > 0:
                sid = oc_create_session()
                oc_warm(sid)
                with _pool_lock:
                    _pool.append(sid)
            else:
                time.sleep(1.0)
        except Exception:
            time.sleep(2.0)


def pool_prime():
    for _ in range(POOL_SIZE):
        try:
            sid = oc_create_session()
            oc_warm(sid)
            with _pool_lock:
                _pool.append(sid)
        except Exception:
            break


def clip(s, n=12000):
    s = s or ""
    return s if len(s) <= n else s[:n] + "\n...[tronque]"


def content_to_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, dict):
                if c.get("type") == "text":
                    out.append(c.get("text", ""))
                elif c.get("type") == "image_url":
                    out.append("[image]")
        return "\n".join(out)
    return str(content)


def extract_images(content):
    if not isinstance(content, list):
        return []
    urls = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "image_url":
            u = c["image_url"]
            if isinstance(u, dict):
                u = u.get("url", "")
            if u:
                urls.append(u)
    return urls


def transcript(messages, last_index=None):
    lines = []
    upto = len(messages) if last_index is None else last_index
    for m in messages[:upto]:
        role = m.get("role") or "user"
        if role == "system":
            t = content_to_text(m.get("content", ""))
            if t.strip():
                lines.append(f"SYSTEM: {clip(t)}")
        elif role == "user":
            t = content_to_text(m.get("content", ""))
            if t.strip():
                lines.append(f"USER: {clip(t)}")
        elif role == "assistant":
            t = content_to_text(m.get("content", ""))
            tcs = m.get("tool_calls") or []
            for tc in tcs:
                fn = tc.get("function", {})
                lines.append(f"ASSISTANT CALLED: {fn.get('name')}({fn.get('arguments', '')})")
            if t.strip():
                lines.append(f"ASSISTANT: {clip(t)}")
        elif role == "tool":
            t = content_to_text(m.get("content", ""))
            if t.strip():
                lines.append(f"TOOL RESULT: {clip(t)}")
    return "\n".join(lines)


def fingerprint(messages):
    h = 7
    for m in messages:
        t = content_to_text(m.get("content", ""))
        s = (m.get("role") or "") + ":" + t[:300]
        for ch in s:
            h = (h * 31 + ord(ch)) % 2147483647
    return str(h)


def build_planner_prompt(messages, tools):
    tools_blob = json.dumps(tools or [], ensure_ascii=False) if tools else "[]  (aucune fonction disponible)"
    history = transcript(messages, last_index=len(messages) - 1)
    current = content_to_text(messages[-1].get("content", ""))
    return PROTOCOL.replace("%TOOLS%", tools_blob).replace("%HISTORY%", history or "(aucun historique)").replace("%USER%", current)


def parse_model_reply(text, allowed_names):
    if not text:
        return ("text", None, None)
    s = text.strip()
    for cand in (s, re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.S)):
        cand = cand.strip()
        start, end = cand.find("{"), cand.rfind("}")
        if 0 <= start < end:
            obj = cand[start:end + 1]
            try:
                j = json.loads(obj)
                if isinstance(j, dict) and isinstance(j.get("name"), str) and isinstance(j.get("arguments"), dict):
                    name = j["name"]
                    if allowed_names is None or name in allowed_names:
                        return ("tool", name, j["arguments"])
                    return ("text", None, None)
                if isinstance(j, dict) and "name" in j and "arguments" in j:
                    args = j["arguments"] if isinstance(j["arguments"], dict) else {}
                    return ("tool", j["name"], args)
            except Exception:
                pass
    return ("text", None, None)


def run_turn(messages, tools):
    allowed = set()
    for t in tools or []:
        fn = t.get("function", {}) if isinstance(t, dict) else {}
        n = fn.get("name") or (t.get("name") if isinstance(t, dict) else None)
        if n:
            allowed.add(n)
    allowed = allowed or None

    key = fingerprint(messages[:-1]) if len(messages) > 1 else "<first>"
    with _lock:
        conv = _convs.get(key)
        if conv is not None:
            sid = conv["sid"]
        else:
            sid = pool_get()
            _convs[key] = {"sid": sid, "created": time.time()}
            if len(_convs) > _MAX_CONVS:
                for k, _ in sorted(_convs.items(), key=lambda kv: kv[1]["created"])[:50]:
                    _convs.pop(k, None)

    prompt = build_planner_prompt(messages, tools)
    parts = []
    for u in extract_images(messages[-1].get("content", "")):
        mime = "image/png"
        low = u.lower()
        if ".jpg" in low or ".jpeg" in low or "image/jpeg" in low:
            mime = "image/jpeg"
        elif ".gif" in low or "image/gif" in low:
            mime = "image/gif"
        elif ".webp" in low or "image/webp" in low:
            mime = "image/webp"
        parts.append({"type": "file", "mime": mime, "url": u})
    parts.append({"type": "text", "text": prompt})

    res = oc_post(f"/session/{sid}/message",
                  {"parts": parts, "model": DEFAULT_MODEL, "tools": ALL_TOOLS_OFF}, timeout=2400)

    texts = []
    for p in res.get("parts", []):
        if p.get("type") in ("text", "reasoning"):
            t = p.get("text")
            if t:
                texts.append(t)
    raw = "\n".join(texts).strip()

    kind, name, args = parse_model_reply(raw, allowed)
    reason = "stop"
    usage = {}
    for p in res.get("parts", []):
        if p.get("type") == "step-finish":
            reason = p.get("reason") or "stop"
            tk = p.get("tokens") or {}
            usage = {"prompt_tokens": tk.get("input", 0), "completion_tokens": tk.get("output", 0),
                     "total_tokens": tk.get("total", 0)}
            break
    if not usage:
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return kind, name, args, raw, usage, reason


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self._send_json({"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": PROVIDER, "created": 0}]})
        elif self.path.startswith("/health"):
            with _pool_lock:
                p = len(_pool)
            self._send_json({"ok": True, "model": MODEL_ID, "provider": PROVIDER, "warm_sessions": p, "conversations": len(_convs)})
        else:
            self._send_json({"error": {"message": "not found", "type": "invalid_request_error"}}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()
        if path.rstrip("/") == "/v1/chat/completions":
            self._handle_chat(body)
        elif path.rstrip("/") == "/v1/embeddings":
            inp = body.get("input")
            items = [inp] if isinstance(inp, str) else (inp or [])
            data = [{"object": "embedding", "index": i, "embedding": [0.0] * 256} for i in range(len(items))]
            self._send_json({"object": "list", "data": data, "model": body.get("model", MODEL_ID)})
        else:
            self._send_json({"error": {"message": "not found", "type": "invalid_request_error"}}, 404)

    def _handle_chat(self, body):
        messages = body.get("messages") or []
        stream = bool(body.get("stream", False))
        tools = body.get("tools") or []
        req_model = body.get("model") or MODEL_ID
        if not messages:
            self._send_json({"error": {"message": "messages required", "type": "invalid_request_error"}}, 400)
            return
        try:
            kind, name, args, raw, usage, reason = run_turn(messages, tools)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            self._send_json({"error": {"message": f"opencode error {e.code}: {detail}", "type": "server_error"}}, 502)
            return
        except Exception as e:
            self._send_json({"error": {"message": f"bridge error: {e}", "type": "server_error"}}, 500)
            return

        created = int(time.time())
        base = {"id": "chatcmpl-" + str(uuid.uuid4()) + str(created), "created": created, "model": req_model}
        chunk_delay = STREAM_CHUNK_MS / 1000.0

        if kind == "tool":
            call_id = "call_" + uuid.uuid4().hex[:12]
            fn = {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}
            if not stream:
                resp = {
                    **base, "object": "chat.completion",
                    "choices": [{"index": 0,
                                 "message": {"role": "assistant", "content": None,
                                             "tool_calls": [{"id": call_id, "type": "function", "function": fn}]},
                                 "finish_reason": "tool_calls"}],
                    "usage": usage,
                }
                self._send_json(resp)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    c0 = {**base, "object": "chat.completion.chunk",
                          "choices": [{"index": 0,
                                       "delta": {"role": "assistant", "content": None,
                                                 "tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": ""}}]},
                                       "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(c0)}\n\n".encode("utf-8"))
                    c1 = {**base, "object": "chat.completion.chunk",
                          "choices": [{"index": 0,
                                       "delta": {"tool_calls": [{"index": 0, "function": {"arguments": fn["arguments"]}}]},
                                       "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(c1)}\n\n".encode("utf-8"))
                    c2 = {**base, "object": "chat.completion.chunk",
                          "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}
                    self.wfile.write(f"data: {json.dumps(c2)}\n\n".encode("utf-8"))
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except Exception:
                    pass
        else:
            text = raw or "[sans reponse]"
            if not stream:
                resp = {**base, "object": "chat.completion",
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": reason}],
                        "usage": usage}
                self._send_json(resp)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    head = {**base, "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(head)}\n\n".encode("utf-8"))
                    for i in range(0, len(text), 12):
                        piece = text[i:i + 12]
                        ch = {**base, "object": "chat.completion.chunk",
                              "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                        self.wfile.write(f"data: {json.dumps(ch)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        if chunk_delay:
                            time.sleep(chunk_delay)
                    last = {**base, "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": reason}]}
                    self.wfile.write(f"data: {json.dumps(last)}\n\n".encode("utf-8"))
                    self.wfile.write(f"data: {json.dumps({'usage': usage})}\n\n".encode("utf-8"))
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except Exception:
                    pass


def main():
    threading.Thread(target=pool_prime, daemon=True).start()
    threading.Thread(target=pool_refill_loop, daemon=True).start()
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    server.daemon_threads = True
    print(f"HERMES-BRAIN bridge v3 on http://{LISTEN_HOST}:{LISTEN_PORT}/v1 -> opencode ({PROVIDER}/{MODEL_ID})")
    print(f"  pool warm sessions: {len(_pool)} | stream chunk: {STREAM_CHUNK_MS}ms | port: {LISTEN_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
