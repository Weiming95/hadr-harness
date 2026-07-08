#!/usr/bin/env python3
"""A tiny Claude Code — a HADR agent harness in ~100 lines of Python.

The harness IS the loop + the tools + the interface. The model is swappable
inside it. Five levels are built up here; see README.md for the map:

  1. chat loop        — read input, send `messages`, print reply      (main)
  2. standing orders  — prepend a system prompt from a file           (SYSTEM)
  3. one tool         — fetch_feed: model asks, we run it, result back (TOOLS)
  4. the agent loop   — keep going while the model requests tools      (inner loop)
  5. a second tool    — write_dashboard: save an assessed HTML page    (TOOLS)

Talks to **OpenCode Go**, which is an OpenAI-compatible endpoint (chat
completions) serving open models (GLM, Kimi, Qwen, DeepSeek, MiniMax, MiMo).
Zero dependencies — Python standard library only. No `pip install`.
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _ssl_context():
    """A TLS context that actually finds a CA bundle.

    The python.org macOS build ships without wired-up system certs, so plain
    urllib often fails with CERTIFICATE_VERIFY_FAILED. Prefer certifi if it is
    installed (`python3 -m pip install certifi`); allow an opt-in escape hatch.
    """
    if os.environ.get("OPENCODE_INSECURE_TLS") == "1":
        return ssl._create_unverified_context()  # opt-in only; see README
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001 — fall back to whatever system certs exist
        pass
    return ctx


SSL_CTX = _ssl_context()

# --- config ------------------------------------------------------------------
# OpenCode Go is OpenAI-compatible. Override any of these with env vars; see
# README.md for where to get your key and how to find a valid model id.
HERE = Path(__file__).parent


def _load_dotenv(path):
    """Minimal .env loader: `KEY=value` lines, `#` comments. A real environment
    variable always wins, so `.env` is a convenience, not an override. Keeps the
    key out of git (see .gitignore) and out of your shell history."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        val = val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:  # never override the real env
            os.environ[key] = val


_load_dotenv(HERE / ".env")

BASE_URL = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
MODEL = os.environ.get("OPENCODE_MODEL", "")  # e.g. kimi-k2 / glm-4.6 — run --models

# Key resolution, best-practice first: the OPENCODE_API_KEY env var wins (so a
# .env or CI secret can override), otherwise fall back to the macOS Keychain —
# encrypted at rest, never in a plaintext file or shell history. Store it with:
#   security add-generic-password -a "$USER" -s opencode-go -w
KEYCHAIN_SERVICE = "opencode-go"


def _read_api_key():
    key = os.environ.get("OPENCODE_API_KEY")
    if key:
        return key
    try:  # macOS only; silent no-op elsewhere
        out = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
             "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


API_KEY = _read_api_key()

# --- Level 2: standing orders. This is all a CLAUDE.md / system prompt is: ---
# a text file we stick on the front of the conversation.
_sys_file = HERE / "system_prompt.md"
SYSTEM = _sys_file.read_text() if _sys_file.exists() else ""

# --- Levels 3 & 5: the tools -------------------------------------------------
# The same public HADR feeds the main project watches (see hadr-project/feeds/).
FEEDS = {
    "usgs": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
    "gdacs": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP",
}


def fetch_feed(feed: str) -> str:
    """Fetch a live HADR feed and hand back a trimmed JSON summary."""
    url = FEEDS.get(feed)
    if not url:
        return f"Unknown feed '{feed}'. Choose one of: {', '.join(FEEDS)}."
    req = urllib.request.Request(url, headers={"User-Agent": "hadr-harness/0.1"})
    with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as r:
        doc = json.loads(r.read().decode())
    feats = doc.get("features", [])
    # Keep the context window small: return a count + the first 20 features.
    return json.dumps({"feed": feed, "total": len(feats), "features": feats[:20]})


def write_dashboard(title: str, events: list, path: str = "dashboard.html") -> str:
    """Save an HTML page of assessed events."""
    rows = "\n".join(
        f"<tr><td>{_esc(e.get('severity',''))}</td>"
        f"<td>{_esc(e.get('headline',''))}</td>"
        f"<td>{_esc(e.get('location',''))}</td>"
        f"<td>{_esc(e.get('assessment',''))}</td></tr>"
        for e in events
    )
    html = (
        f"<!doctype html><meta charset=utf-8><title>{_esc(title)}</title>"
        "<style>body{font:15px system-ui;margin:2rem}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.4rem .6rem}</style>"
        f"<h1>{_esc(title)}</h1><table><tr><th>Severity</th><th>Event</th>"
        f"<th>Location</th><th>Assessment</th></tr>{rows}</table>"
    )
    out = HERE / path
    out.write_text(html)
    return f"Wrote {len(events)} events to {out}"


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(text: str) -> str:
    """Send a plain-text message to the configured Telegram chat."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return "Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)."
    # If a published dashboard URL is configured, append it as a tappable link.
    url = os.environ.get("DASHBOARD_URL")
    if url:
        text = f"{text}\n\n📊 Full dashboard: {url}"
    payload = {"chat_id": chat_id, "text": text[:4096], "disable_web_page_preview": True}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as r:
            r.read()
        return f"Sent Telegram message ({len(text)} chars) to chat {chat_id}."
    except urllib.error.HTTPError as e:
        return f"Telegram send failed ({e.code}): {e.read().decode()[:200]}"


# Tool schemas the model sees (OpenAI function-calling format).
def _fn(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOLS = [
    _fn("fetch_feed", "Fetch a live HADR disaster feed and return a trimmed JSON summary.",
        {"feed": {"type": "string", "enum": list(FEEDS)}}, ["feed"]),
    _fn("write_dashboard", "Save an HTML dashboard of assessed disaster events.",
        {"title": {"type": "string"},
         "events": {"type": "array", "items": {"type": "object", "properties": {
             "severity": {"type": "string"}, "headline": {"type": "string"},
             "location": {"type": "string"}, "assessment": {"type": "string"}}}}},
        ["title", "events"]),
    _fn("send_telegram", "Send a concise plain-text briefing to the duty officer's Telegram chat.",
        {"text": {"type": "string"}}, ["text"]),
]
DISPATCH = {
    "fetch_feed": fetch_feed,
    "write_dashboard": write_dashboard,
    "send_telegram": send_telegram,
}


# A browser-like User-Agent: the endpoint sits behind Cloudflare, which blocks
# the default Python-urllib agent with "error code: 1010".
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _auth_headers(extra=None):
    h = {"authorization": f"Bearer {API_KEY}", "user-agent": UA}
    if extra:
        h.update(extra)
    return h


# --- the model call: raw HTTP, no SDK. This is the whole "magic". ------------
def _post(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=_auth_headers({"content-type": "application/json"}),
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"\nAPI error {e.code}: {e.read().decode()[:600]}")
    except urllib.error.URLError as e:
        sys.exit(f"\nNetwork/TLS error: {e.reason}. If it's a certificate error, run "
                 f"`python3 -m pip install certifi`.")


def call_model(messages: list) -> dict:
    payload = {"model": MODEL, "messages": messages, "tools": TOOLS, "max_tokens": 2048}
    data = _post(f"{BASE_URL}/chat/completions", payload)
    return data["choices"][0]["message"]


# --- Levels 3 & 4: one full agent turn (run tools until the model is done) ---
def converse(messages: list, user: str) -> None:
    messages.append({"role": "user", "content": user})
    # Level 4: keep going while the model keeps requesting tools.
    while True:
        msg = call_model(messages)
        messages.append(msg)  # append the assistant turn verbatim (incl. tool_calls)

        if msg.get("content"):
            print(f"\nassistant> {msg['content']}\n")

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return  # the model is done for this turn

        # Level 3: run each requested tool, feed the result back in.
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"].get("arguments") or "{}")
            fn = DISPATCH.get(name)
            print(f"  [tool] {name}({json.dumps(args)[:80]})")
            try:
                out = fn(**args) if fn else f"unknown tool {name}"
            except Exception as ex:  # noqa: BLE001 — surface any failure to the model
                out = f"tool error: {ex}"
            print(f"    └─ {str(out)[:120]}")  # echo the result (useful in CI logs)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(out)})


def _require_config():
    if not API_KEY:
        sys.exit("No API key found. Store it in the Keychain:\n"
                 "  security add-generic-password -a \"$USER\" -s opencode-go -w\n"
                 "or set OPENCODE_API_KEY / .env. See README.md ('Where to put your key').")
    if not MODEL:
        sys.exit("Set OPENCODE_MODEL to a Go model id. Run `python3 harness.py --models` to list them.")


def _fresh_messages():
    # Level 1: the conversation IS this list. Level 2: system prompt goes first.
    return [{"role": "system", "content": SYSTEM}] if SYSTEM else []


# --- Level 1: the interactive loop -------------------------------------------
def main():
    _require_config()
    messages = _fresh_messages()
    print(f"HADR harness ({MODEL}) — ask me to check feeds and build a dashboard. Ctrl-C to quit.\n")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user:
            converse(messages, user)


# Non-interactive: run one prompt and exit. This is what the 08:30 cron calls.
DEFAULT_PROMPT = (
    "Fetch the USGS and GDACS feeds, assess the current worldwide disaster picture, "
    "call write_dashboard to save a morning situation report of the most serious events, "
    "and call send_telegram with a concise plain-text briefing of them. "
    "Then give a one-paragraph summary."
)


def run_once(prompt: str) -> None:
    _require_config()
    print(f"[once] {MODEL}: {prompt}\n")
    converse(_fresh_messages(), prompt or DEFAULT_PROMPT)


def list_models():
    """Discover valid Go model ids (OpenAI-compatible /models endpoint)."""
    if not API_KEY:
        sys.exit("No API key found (Keychain or OPENCODE_API_KEY). See README.md.")
    req = urllib.request.Request(f"{BASE_URL}/models", headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Couldn't list models ({e.code}). Open the OpenCode TUI, run /connect → "
                 f"OpenCode Go to see model ids, or check https://opencode.ai/docs/go/")
    ids = [m.get("id") for m in data.get("data", [])]
    print("Available Go models — set one as OPENCODE_MODEL:\n  " + "\n  ".join(ids or ["(none returned)"]))


def telegram_chat_ids():
    """Print chat ids from recent messages, so you can find TELEGRAM_CHAT_ID.
    First send your bot a message (any text), then run this."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Set TELEGRAM_BOT_TOKEN first (in .env), then send your bot a message.")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getUpdates")
    with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as r:
        data = json.loads(r.read().decode())
    chats = {}
    for upd in data.get("result", []):
        chat = (upd.get("message") or upd.get("channel_post") or {}).get("chat", {})
        if chat.get("id"):
            chats[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name", "")
    if not chats:
        print("No chats found. Send your bot a message first (open it and type /start), then re-run.")
        return
    print("Chats that have messaged your bot — set one as TELEGRAM_CHAT_ID:")
    for cid, who in chats.items():
        print(f"  {cid}  ({who})")


if __name__ == "__main__":
    if "--models" in sys.argv:
        list_models()
    elif "--tg-updates" in sys.argv:
        telegram_chat_ids()
    elif "--once" in sys.argv:
        i = sys.argv.index("--once")
        run_once(" ".join(sys.argv[i + 1:]).strip())
    else:
        main()
