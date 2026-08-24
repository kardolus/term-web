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

## Security — read before deploying

**This app hands out a real shell** on the SSH target host to anyone who
passes Keycloak OIDC and the `ALLOWED_EMAILS` allow-list. Threat model, honestly:

- A compromised IdP account on the allow-list = a shell on your host. There is
  no command filtering and no audit log beyond your shell history.
- `SESSION_SECRET` signs the login cookie; whoever holds it can mint sessions.
  The server refuses to start with the dev default unless `TERMWEB_DEV=1`.
- The pod holds a private SSH key to the host and read-only mounts of your
  session archive — transcripts routinely contain secrets.
- This is a homelab project. It has not had a formal security audit; assume
  the terminal stack (Starlette + xterm.js + PTY bridge) may have bugs.

Hardening that is on by default: OIDC with a confidential client, an email
allow-list, one-time 30s WebSocket tickets, an Origin check, pinned
`known_hosts`, no client-supplied command ever reaching a shell, and only
`/healthz` + `/favicon.svg` unauthenticated. Recommended on top: a dedicated
low-privilege SSH user, exact redirect URIs in the IdP client, and keeping the
app reachable only via a network layer you control (VPN/tunnel).

## Adapting this

Built for one homelab (defaults name `kardol.us`, `forge`, `10.0.0.120`,
`guillermo`) — **every one of them must be overridden for your setup**, via the
env vars in `src/termweb/config.py` and the manifest in
`deploy/k8s/10-term-web.yaml` (its header lists the prereqs: Keycloak
confidential client, SSH keypair to the host, k8s secrets, ingress with long
proxy timeouts for the WebSocket). The session picker expects an archive laid
out by [agent-sessions](https://github.com/kardolus/agent-sessions)
(`<host>/<project-slug>/<uuid>.jsonl`).

## License

MIT — see [LICENSE](LICENSE).
