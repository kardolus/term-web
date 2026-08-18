# term-web

Browser terminal for **Claude Code / Codex on forge** at **term.kardol.us**, with a
session picker. Single-user (Keycloak OIDC, `ALLOWED_EMAILS=g@kardol.us`).

## How it works

- **Picker** (`/`): archived Claude sessions (the claude-sessions archive on forge —
  all machines), forge-local Codex rollouts, running tmux sessions (reattach), and
  new-session launch with a `~/workspace` dir choice. Every session row can open in
  **either agent**: native resume, or cross-open via a transcript **handoff digest**
  staged at `~/.cache/term-web/` on forge. A **search box** over the claude archive
  (`/api/search?q=`) does a live ranked full-text scan of conversation text — all
  terms must match, snippets highlighted, results open like any other row (same
  semantics as `claude-sessions search`).
- **Terminal** (`/t/<name>`): xterm.js ⇄ WebSocket ⇄ pod PTY ⇄ `ssh -tt` ⇄
  `tmux new -A` on the forge host as guillermo. tmux is the persistence layer:
  closing the tab detaches; the agent keeps running.
- **Auth**: health-web's ringer pattern (authlib OIDC + itsdangerous cookie, 3d TTL)
  plus, for the WS, a one-time 30s ticket from `POST /api/terminal` and an Origin
  check. No GET has side effects; no client-supplied command ever reaches a shell.

## Layout

- `src/termweb/{server,auth,config,sessions,handoff,terminal,ui}.py`
- `deploy/k8s/10-term-web.yaml` — Deployment (ro hostPath mounts of
  `~/claude-sessions`, `~/.codex/sessions`, `~/workspace` + `term-ssh` secret),
  Service, Ingress (the 3600s proxy timeouts are the WS lifeline). Prereqs in the
  manifest header.

## Dev

```bash
uv sync && uv run pytest
SESSION_SECRET=x uv run python -m termweb.server  # localhost:8000
```

## Deploy (on forge)

```bash
docker build -t ghcr.io/kardolus/term-web:vN . && docker push ghcr.io/kardolus/term-web:vN
kubectl --context forge -n term set image deploy/term-web term-web=ghcr.io/kardolus/term-web:vN
```
