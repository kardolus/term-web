"""Target validation → remote tmux command, one-time spawn tickets, and the
PTY ⇄ WebSocket bridge (pod pty → ssh -tt → tmux on the forge host).

No client-supplied command ever reaches a shell: every remote command is
assembled here from regex/allow-list-validated tokens and shlex-quoted.
"""

import asyncio
import fcntl
import os
import pty
import secrets
import shlex
import struct
import termios
import time

from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config, handoff, sessions

# `~/.local/bin` is NOT on the non-interactive ssh PATH, and `claude-sessions
# open` ends in `exec claude` by bare name — this prefix is load-bearing.
_ENV = 'env PATH="$HOME/.local/bin:$PATH"'
_HANDOFF_DIR = ".cache/term-web"
# Single-user terminal behind SSO on the owner's own host — agents run with
# permission prompts / sandboxing off by explicit owner choice.
_AGENT_CMD = {
    "claude": "claude --dangerously-skip-permissions",
    "codex": "codex --dangerously-bypass-approvals-and-sandbox",
}

_tickets = URLSafeTimedSerializer(config.SESSION_SECRET, salt="term-ticket")
_seen_nonces: dict[str, float] = {}
active_terminals = 0


class TargetError(ValueError):
    pass


def _remote_transcript_path(local_path: str) -> str:
    """Map a pod ro-mount path back to its real path on forge (for the digest footer)."""
    for local_root, remote_root in (
        (config.CLAUDE_ARCHIVE_DIR, f"{config.REMOTE_HOME}/claude-sessions"),
        (config.CODEX_SESSIONS_DIR, f"{config.REMOTE_HOME}/.codex/sessions"),
    ):
        if local_path.startswith(local_root + "/"):
            return remote_root + local_path[len(local_root):]
    return local_path


async def resolve_target(body: dict) -> dict:
    """Validate a picker request → a self-contained target dict (goes into the
    ticket). Cross-open targets stage their handoff file on forge here."""
    kind = body.get("kind")

    if kind == "claude":  # archived claude session, native resume
        uuid = body.get("uuid", "")
        path = sessions.find_claude_transcript(uuid) if sessions.UUID_RE.match(uuid) else None
        if not path:
            raise TargetError("unknown claude session")
        return {"kind": kind, "uuid": uuid,
                "cwd": sessions.localize_cwd(sessions.claude_cwd(path)),
                "name": f"cs-{uuid[:8]}"}

    if kind == "codex":  # forge-local codex session, native resume
        uuid = body.get("uuid", "")
        rollout = sessions.find_codex_rollout(uuid) if sessions.UUID_RE.match(uuid) else None
        if not rollout:
            raise TargetError("unknown codex session")
        cwd, _ = sessions._codex_meta_and_preview(rollout)
        return {"kind": kind, "uuid": uuid, "cwd": sessions.localize_cwd(cwd),
                "name": f"cx-{uuid[:8]}"}

    if kind == "cross":  # open a session with the OTHER agent, via handoff digest
        uuid = body.get("uuid", "")
        source = body.get("source")
        if source not in ("claude", "codex") or not sessions.UUID_RE.match(uuid):
            raise TargetError("bad cross-open request")
        path = (sessions.find_claude_transcript(uuid) if source == "claude"
                else sessions.find_codex_rollout(uuid))
        if not path:
            raise TargetError(f"unknown {source} session")
        cwd, digest = handoff.build_digest(source, path, _remote_transcript_path(path))
        remote_file = f"{_HANDOFF_DIR}/handoff-{uuid[:8]}.md"
        await _stage_handoff(remote_file, digest)
        prefix = "xs" if source == "codex" else "xc"
        return {"kind": kind, "agent": "claude" if source == "codex" else "codex",
                "cwd": sessions.localize_cwd(cwd), "handoff": remote_file,
                "name": f"{prefix}-{uuid[:8]}"}

    if kind == "new":
        agent = body.get("agent")
        workdir = body.get("workdir", "~")
        if agent not in ("claude", "codex") or workdir not in sessions.list_workdirs():
            raise TargetError("bad new-session request")
        rand = secrets.token_hex(2)
        safe_dir = "home" if workdir == "~" else workdir.replace(".", "-")
        return {"kind": kind, "agent": agent, "workdir": workdir,
                "name": f"new-{agent}-{safe_dir}-{rand}"}

    raise TargetError("unknown kind")


def build_remote_command(target: dict) -> str:
    """The agent runs directly on the ssh pty — no tmux. Sessions persist on
    disk (claude/codex resume), so closing the tab just means resuming from
    the picker; in exchange there is exactly one client, sized to YOUR
    browser, with none of tmux's multi-client size clamping."""
    kind = target["kind"]
    if kind == "claude":
        # `claude-sessions open` would exec claude with no flag passthrough, so
        # import via `pull` (echoes the project path) and invoke claude
        # ourselves. pull refuses when the forge-local copy is newer (a
        # just-used session before the 5-min sync) — fall back to the
        # recorded cwd, where that newer local copy lives.
        uuid = target["uuid"]
        return (f'proj="$({_ENV} CLAUDE_SESSIONS_REMOTE=local '
                f'claude-sessions pull {uuid})" || proj={shlex.quote(target["cwd"])}; '
                f'cd "$proj" || cd "$HOME"; '
                f'{_ENV} {_AGENT_CMD["claude"]} --resume {uuid}')
    if kind == "codex":
        return (f"cd {shlex.quote(target['cwd'])} || cd \"$HOME\"; "
                f"{_ENV} codex resume --dangerously-bypass-approvals-and-sandbox "
                f"{target['uuid']}")
    if kind == "cross":
        prompt = (f"Read ~/{target['handoff']} — a transcript digest of a prior "
                  f"session in this directory by another coding agent. "
                  f"Continue that work.")
        return (f"cd {shlex.quote(target['cwd'])} || cd \"$HOME\"; "
                f"{_ENV} {_AGENT_CMD[target['agent']]} {shlex.quote(prompt)}")
    if kind == "new":
        wd = "$HOME" if target["workdir"] == "~" else f"$HOME/workspace/{target['workdir']}"
        return f'cd "{wd}" && {_ENV} {_AGENT_CMD[target["agent"]]}'
    raise TargetError("unknown kind")


# ------------------------------------------------------------------ tickets

def mint_ticket(email: str, target: dict) -> str:
    return _tickets.dumps({"e": email, "t": target, "n": secrets.token_hex(8)})


def redeem_ticket(token: str, email: str) -> dict | None:
    """One-time: a nonce is burned on first successful redeem."""
    try:
        data = _tickets.loads(token, max_age=config.TICKET_MAX_AGE_S)
    except BadSignature:
        return None
    nonce = data.get("n")
    now = time.monotonic()
    for n, t in list(_seen_nonces.items()):  # expire old nonces
        if now - t > config.TICKET_MAX_AGE_S * 2:
            del _seen_nonces[n]
    if not nonce or nonce in _seen_nonces or data.get("e") != email:
        return None
    _seen_nonces[nonce] = now
    return data.get("t")


# ------------------------------------------------------------------ staging

async def _stage_handoff(remote_file: str, content: str) -> None:
    cmd = sessions._ssh_base() + [
        "--",
        f"mkdir -p ~/{_HANDOFF_DIR} && "
        f"find ~/{_HANDOFF_DIR} -name 'handoff-*.md' -mtime +7 -delete; "
        f"cat > ~/{shlex.quote(remote_file)}",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await asyncio.wait_for(proc.communicate(content.encode()), timeout=20)
    if proc.returncode != 0:
        raise TargetError(f"handoff staging failed: {err.decode()[:200]}")


# ------------------------------------------------------------------ bridge

def _set_winsize(fd: int, cols: int, rows: int) -> None:
    cols = max(2, min(cols, 500))
    rows = max(2, min(rows, 300))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


async def bridge(ws, target: dict) -> None:
    """Pump bytes between an accepted WebSocket and an ssh-to-tmux PTY.
    Caller has already authenticated and accepted the socket."""
    global active_terminals
    from starlette.websockets import WebSocketDisconnect

    loop = asyncio.get_event_loop()
    remote_cmd = build_remote_command(target)

    master, slave = pty.openpty()
    _set_winsize(master, 80, 24)
    proc = await asyncio.create_subprocess_exec(
        "ssh", "-tt", "-i", config.SSH_KEY,
        "-o", f"UserKnownHostsFile={config.SSH_KNOWN_HOSTS}",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=4",
        f"{config.SSH_USER}@{config.SSH_HOST}", "--", remote_cmd,
        stdin=slave, stdout=slave, stderr=slave,
        start_new_session=True,
        env={**os.environ, "TERM": "xterm-256color"},
    )
    os.close(slave)
    active_terminals += 1
    last_activity = time.monotonic()

    async def pump_output():
        nonlocal last_activity
        while True:
            try:
                chunk = await loop.run_in_executor(None, os.read, master, 65536)
            except OSError:
                return
            if not chunk:
                return
            last_activity = time.monotonic()
            await ws.send_bytes(chunk)

    async def pump_input():
        nonlocal last_activity
        while True:
            msg = await ws.receive_json()
            last_activity = time.monotonic()
            if msg.get("t") == "i":
                os.write(master, str(msg.get("d", "")).encode())
            elif msg.get("t") == "r":
                _set_winsize(master, int(msg.get("cols", 80)), int(msg.get("rows", 24)))

    async def watchdog():
        while True:
            await asyncio.sleep(60)
            if time.monotonic() - last_activity > config.IDLE_TIMEOUT_S:
                return

    out_task = asyncio.ensure_future(pump_output())
    in_task = asyncio.ensure_future(pump_input())
    dog_task = asyncio.ensure_future(watchdog())
    try:
        done, _pending = await asyncio.wait(
            [out_task, in_task, dog_task], return_when=asyncio.FIRST_COMPLETED)
        if out_task in done:  # child exited (user quit the agent / tmux gone)
            rc = await proc.wait()
            try:
                await ws.send_json({"t": "exit", "code": rc})
                await ws.close(code=1000)
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        for t in (out_task, in_task, dog_task):
            t.cancel()
        await asyncio.gather(out_task, in_task, dog_task, return_exceptions=True)
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        try:
            os.close(master)
        except OSError:
            pass
        active_terminals -= 1
