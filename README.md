# HADR harness — a tiny Claude Code in ~100 lines

[![morning briefing](https://github.com/Weiming95/hadr-harness/actions/workflows/morning-briefing.yml/badge.svg)](https://github.com/Weiming95/hadr-harness/actions/workflows/morning-briefing.yml)

Build the thing you've been *using*. This is a minimal agent **harness**: a chat
loop, a system prompt, three tools, and an agent loop — with the model swappable
inside it. It watches the same HADR feeds as the main project (USGS, GDACS),
assesses them, saves a dashboard, and messages a briefing to Telegram. It shares
no code with the main project: separate repo, Python standard library only, no
`pip install` required.

Runs interactively, one-shot (`--once`), or on a schedule — a GitHub Action
sends a briefing to Telegram every day at **08:30 Singapore time**.

> The harness is the loop, the tools, and the interface. The model is just a
> text-in / text-out function you call in the middle of it.

## Talks to OpenCode **Go**

OpenCode **Go** (the $10/mo plan) is different from OpenCode **Zen**:

- It's an **OpenAI-compatible** endpoint (`chat/completions`), base URL
  `https://opencode.ai/zen/go/v1`, auth `Authorization: Bearer <key>`.
- It serves **open-weight models** — GLM, Kimi, Qwen, DeepSeek, MiniMax, MiMo.
  **No Claude/Anthropic models** on Go. This harness therefore speaks the
  OpenAI function-calling format, not Anthropic's.

## Where to put your OpenCode Go API key

**Get the key first.** Sign in to OpenCode Zen at <https://opencode.ai/auth>,
**subscribe to Go**, and copy your API key. (In the OpenCode TUI it's the key
you paste after `/connect` → *OpenCode Go*.)

Then store it. The harness resolves the key in this order: `OPENCODE_API_KEY`
env var → a `.env` file (auto-loaded) → macOS Keychain. Pick **one**:

### Best practice — macOS Keychain (encrypted, no plaintext, no shell history)

Store it once (the `-w` flag prompts for the value with hidden input, so the key
never lands in your shell history):

```sh
security add-generic-password -a "$USER" -s opencode-go -w
# paste the key at the prompt, press Enter
```

That's it — `python3 harness.py` reads it automatically. To rotate the key:

```sh
security delete-generic-password -a "$USER" -s opencode-go
security add-generic-password -a "$USER" -s opencode-go -w
```

### Alternative A — a gitignored `.env` (plaintext on disk, kept out of git)

`harness.py` auto-loads `.env`, so no `source` needed. Copy the template and fill
it in:

```sh
cp .env.example .env
# edit .env: OPENCODE_API_KEY=…, OPENCODE_MODEL=…, and optionally the Telegram vars
python3 harness.py
```

### Alternative B — shell profile (simplest, least private)

Add to `~/.zshrc` (plaintext, and injected into every process's environment):

```sh
export OPENCODE_API_KEY="paste-your-key-here"
```
A nicer variant keeps the secret in the Keychain and only the *lookup* in your rc:
```sh
export OPENCODE_API_KEY="$(security find-generic-password -a "$USER" -s opencode-go -w 2>/dev/null)"
```

> Never hardcode the key in `harness.py`, and never commit it. `.env`, `*.key`,
> and `key.txt` are gitignored as a backstop.

### Pick a model (required — Go has no default here)

Discover valid ids, then set one:

```sh
python3 harness.py --models
export OPENCODE_MODEL="kimi-k2.7-code"   # use an exact id from --models
```

Prefer a strong tool-using model (Kimi, GLM, or Qwen) — the agent loop only
works if the model actually emits function calls.

If `--models` can't reach the endpoint, open the OpenCode TUI and run
`/connect` → *OpenCode Go* to see the exact model ids, and check
<https://opencode.ai/docs/go/>.

## One-time setup on macOS (fixes the SSL error)

The python.org macOS build ships without a wired-up certificate bundle, so the
first network call fails with `CERTIFICATE_VERIFY_FAILED`. Fix it once:

```sh
python3 -m pip install certifi
```

The harness auto-detects `certifi`. (Or run the `Install Certificates.command`
in your `/Applications/Python 3.x/` folder.) For a throwaway experiment only,
`export OPENCODE_INSECURE_TLS=1` bypasses verification — don't leave it on.

## Run it

```sh
python3 harness.py
```

Then try:

```
you> what's the current earthquake picture?
you> assess the most serious ones and write me a dashboard
```

It will `fetch_feed("usgs")`, reason over the result, maybe fetch GDACS too,
`write_dashboard(...)` → `dashboard.html` in this folder, and (if configured)
`send_telegram(...)` a short briefing. Open the HTML file.

### Run modes

| Command | What it does |
|---|---|
| `python3 harness.py` | Interactive chat loop |
| `python3 harness.py --once "<prompt>"` | Run one prompt and exit (what the cron uses). With no prompt, uses a default morning-briefing prompt. |
| `python3 harness.py --models` | List valid OpenCode Go model ids |
| `python3 harness.py --tg-updates` | Show chat ids that have messaged your bot (to find `TELEGRAM_CHAT_ID`) |

## Telegram delivery (optional)

The `send_telegram` tool pushes a plain-text briefing to a Telegram chat.

1. **Create a bot** — message [@BotFather](https://t.me/BotFather), send
   `/newbot`, and copy the **token** it gives you.
2. **Start a chat** — open your new bot and tap **Start** (or send any message),
   so it can see your chat.
3. **Configure** — set `TELEGRAM_BOT_TOKEN` (in `.env` or the environment), then
   find your chat id:
   ```sh
   python3 harness.py --tg-updates      # prints chat ids that messaged the bot
   ```
   and set `TELEGRAM_CHAT_ID` to the value shown.

If the Telegram vars are unset, the harness still runs — `send_telegram` just
reports "not configured" and the briefing is skipped.

## Scheduled: the 08:30 SGT morning briefing

`.github/workflows/morning-briefing.yml` runs the harness once a day via cron
(`30 0 * * *` UTC = **08:30 Asia/Singapore**), plus a manual **Run workflow**
button. Each run fetches USGS + GDACS, assesses, writes the dashboard, and sends
the briefing to Telegram; `dashboard.html` is uploaded as a downloadable
artifact.

Set these repo **Actions secrets** (Settings → Secrets and variables → Actions),
e.g. with the `gh` CLI:

```sh
gh secret set OPENCODE_API_KEY   --repo <owner>/hadr-harness
gh secret set TELEGRAM_BOT_TOKEN --repo <owner>/hadr-harness
gh secret set TELEGRAM_CHAT_ID   --repo <owner>/hadr-harness
```

> GitHub cron is UTC and scheduled runs can start a few minutes late; they also
> pause after ~60 days of repo inactivity (a push or manual run re-arms them).

## The five levels (each a working checkpoint)

The single file `harness.py` is the finished Level 5, but it's commented so you
can see what each level contributes:

| Level | Idea | Where in the code |
|------:|------|-------------------|
| 1 | **Chat loop** — the conversation *is* a `messages` list you resend each turn | `main()` |
| 2 | **Standing orders** — a system prompt prepended as the first message. *This is all a `CLAUDE.md` is.* | `SYSTEM` ← `system_prompt.md` |
| 3 | **One tool** — `fetch_feed`: the model asks, your code runs it, the result goes back into `messages` | `fetch_feed`, `TOOLS`, tool handling |
| 4 | **The agent loop** — keep running tools while the model keeps requesting them (the loop `/goal` wraps a checker around) | `while True:` inside `main()` |
| 5 | **A second tool** — `write_dashboard`: save an assessed HTML page | `write_dashboard` |

To *feel* an earlier checkpoint, comment out `write_dashboard` from `TOOLS`
(Level 4), or drop `"tools"` from the request and the tool handling (Levels 1–2).

**Level 6 (bonus): a third tool** — `send_telegram` pushes the briefing to your
phone, showing that adding a capability is just another entry in `TOOLS` +
`DISPATCH`. The scheduled Action is the same harness run non-interactively
(`--once`), so "an agent on a cron" is nothing more than the loop with no human
at the keyboard.

## How it relates to the main HADR project

Same problem, opposite architecture — on purpose:

- **The Node project (Slice 1)** keeps the model *out* of the decision path: a
  deterministic pipeline (ingest → normalize → correlate → project → score →
  publish) that's replayable and testable.
- **This harness** puts the model *in charge*: it decides when to call
  `fetch_feed`, `write_dashboard`, and `send_telegram`.

`fetch_feed` points at the same live endpoints documented in
`hadr-project/feeds/` — the shared thing is the data and the domain
understanding, not the codebase.

## Files

- `harness.py` — the whole harness (stdlib only): the loop, three tools, and the
  `--once` / `--models` / `--tg-updates` entry points.
- `system_prompt.md` — the standing orders (Level 2). Edit freely.
- `.env.example` — template for local config (copy to `.env`, which is gitignored).
- `.github/workflows/morning-briefing.yml` — the 08:30 SGT scheduled run.
- `dashboard.html` — produced by `write_dashboard` (gitignored; not committed).

## Troubleshooting

- **`API error 401/403`** — key missing/wrong, or Go subscription inactive.
  Re-check `OPENCODE_API_KEY`.
- **`API error 404` / unknown model** — set a valid `OPENCODE_MODEL`
  (`python3 harness.py --models`).
- **`CERTIFICATE_VERIFY_FAILED`** — run the certifi step above.
- **Model replies but never calls a tool** — switch to a stronger tool-using
  model (Kimi / GLM / Qwen); some smaller open models handle function calls
  poorly.
- **Auth rejected despite a valid key** — a few gateways want the model id
  namespaced as `opencode-go/<id>`; try that in `OPENCODE_MODEL`.
- **No Telegram message** — check the run log for the `send_telegram` result
  line (`└─ Sent Telegram message …` vs a failure). Common causes: you haven't
  messaged the bot yet, or `TELEGRAM_CHAT_ID` is wrong (`--tg-updates` shows it).
