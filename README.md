# HADR harness — a tiny Claude Code in ~100 lines

Build the thing you've been *using*. This is a minimal agent **harness**: a chat
loop, a system prompt, two tools, and an agent loop — with the model swappable
inside it. It watches the same HADR feeds as the main project (USGS, GDACS) but
shares no code with it: separate project, Python standard library only, no
`pip install` required.

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
env var → macOS Keychain. Pick **one**:

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

```sh
echo 'OPENCODE_API_KEY=paste-your-key-here' > .env   # .env is already gitignored
set -a; source .env; set +a                          # load it into this shell
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

It will `fetch_feed("usgs")`, reason over the result, maybe fetch GDACS too, and
`write_dashboard(...)` → `dashboard.html` in this folder. Open that file.

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

## How it relates to the main HADR project

Same problem, opposite architecture — on purpose:

- **The Node project (Slice 1)** keeps the model *out* of the decision path: a
  deterministic pipeline (ingest → normalize → correlate → project → score →
  publish) that's replayable and testable.
- **This harness** puts the model *in charge*: it decides when to call
  `fetch_feed` and `write_dashboard`.

`fetch_feed` points at the same live endpoints documented in
`hadr-project/feeds/` — the shared thing is the data and the domain
understanding, not the codebase.

## Files

- `harness.py` — the whole harness (~110 lines, stdlib only).
- `system_prompt.md` — the standing orders (Level 2). Edit freely.
- `dashboard.html` — produced by `write_dashboard` when you ask for one.

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
