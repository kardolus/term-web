"""Session listings, read from the hostPath mounts (claude archive, codex
rollouts, workspace) plus one ssh round-trip for live tmux sessions.

The claude listing is a port of the embedded Python block in the
claude-sessions CLI (`cmd_list`), emitting dicts instead of fixed-width text.
"""

import json
import os
import re
import subprocess
import time

from . import config

UUID_RE = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
TMUX_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ROLLOUT_RE = re.compile(
    r"^rollout-(?P<ts>[\dT-]+)-(?P<uuid>[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.jsonl$"
)


def _claude_preview(path: str) -> str:
    """First real user message, CLI preview rules: skip '<'/'Caveat:' prefixes, 70 chars."""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "user":
                    continue
                msg = obj.get("message") or {}
                c = msg.get("content")
                if isinstance(c, list):
                    c = next((p.get("text", "") for p in c
                              if isinstance(p, dict) and p.get("type") == "text"), "")
                if not isinstance(c, str):
                    continue
                c = c.strip()
                if not c or c.startswith("<") or c.startswith("Caveat:"):
                    continue
                return " ".join(c.split())[:70]
    except OSError:
        pass
    return ""


def list_claude(root: str | None = None) -> list[dict]:
    root = root or config.CLAUDE_ARCHIVE_DIR
    rows = []
    if not os.path.isdir(root):
        return rows
    for host in sorted(os.listdir(root)):
        hostdir = os.path.join(root, host)
        if not os.path.isdir(hostdir):
            continue
        for slug in os.listdir(hostdir):
            slugdir = os.path.join(hostdir, slug)
            if not os.path.isdir(slugdir):
                continue
            for f in os.listdir(slugdir):
                if not f.endswith(".jsonl"):
                    continue
                path = os.path.join(slugdir, f)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                rows.append({
                    "mtime": st.st_mtime,
                    "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                    "host": host,
                    "slug": slug,
                    "project": slug.split("-")[-1] or slug,
                    "uuid": f[:-6],
                    "kb": st.st_size // 1024,
                    "preview": _claude_preview(path),
                })
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows


def find_claude_transcript(uuid: str, root: str | None = None) -> str | None:
    """Newest archived copy of a uuid across hosts (mirrors the CLI's fetch_remote)."""
    root = root or config.CLAUDE_ARCHIVE_DIR
    best, best_mtime = None, -1.0
    if not os.path.isdir(root):
        return None
    for host in os.listdir(root):
        hostdir = os.path.join(root, host)
        if not os.path.isdir(hostdir):
            continue
        for slug in os.listdir(hostdir):
            path = os.path.join(hostdir, slug, f"{uuid}.jsonl")
            try:
                mt = os.stat(path).st_mtime
            except OSError:
                continue
            if mt > best_mtime:
                best, best_mtime = path, mt
    return best


def list_codex(root: str | None = None) -> list[dict]:
    root = root or config.CODEX_SESSIONS_DIR
    rows = []
    if not os.path.isdir(root):
        return rows
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            m = _ROLLOUT_RE.match(f)
            if not m:
                continue
            path = os.path.join(dirpath, f)
            try:
                st = os.stat(path)
            except OSError:
                continue
            cwd, preview = _codex_meta_and_preview(path)
            rows.append({
                "mtime": st.st_mtime,
                "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                "uuid": m.group("uuid"),
                "cwd": cwd,
                "kb": st.st_size // 1024,
                "preview": preview,
            })
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows


def find_codex_rollout(uuid: str, root: str | None = None) -> str | None:
    root = root or config.CODEX_SESSIONS_DIR
    if not os.path.isdir(root):
        return None
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            m = _ROLLOUT_RE.match(f)
            if m and m.group("uuid") == uuid:
                return os.path.join(dirpath, f)
    return None


def _codex_meta_and_preview(path: str) -> tuple[str, str]:
    cwd, preview = "", ""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") == "session_meta" and not cwd:
                    cwd = (obj.get("payload") or {}).get("cwd", "")
                    continue
                if obj.get("type") != "response_item":
                    continue
                payload = obj.get("payload") or {}
                if payload.get("type") != "message" or payload.get("role") != "user":
                    continue
                text = " ".join(
                    p.get("text", "") for p in payload.get("content", [])
                    if isinstance(p, dict) and p.get("type") == "input_text"
                ).strip()
                if not text or text.startswith("<") or text.startswith("#"):
                    continue
                preview = " ".join(text.split())[:70]
                break
    except OSError:
        pass
    return cwd, preview


def localize_cwd(cwd: str) -> str:
    """Rewrite a recorded /Users/x or /home/x prefix to forge's home (CLI's rule)."""
    if not cwd:
        return config.REMOTE_HOME
    m = re.match(r"^/(Users|home)/[^/]+", cwd)
    if m and m.group(0) != config.REMOTE_HOME:
        return config.REMOTE_HOME + cwd[m.end():]
    return cwd


def _ssh_base() -> list[str]:
    return [
        "ssh", "-i", config.SSH_KEY,
        "-o", f"UserKnownHostsFile={config.SSH_KNOWN_HOSTS}",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        f"{config.SSH_USER}@{config.SSH_HOST}",
    ]


def list_tmux() -> list[dict]:
    try:
        out = subprocess.run(
            _ssh_base() + ["--", "/usr/bin/tmux", "list-sessions", "-F",
                           "#{session_name}\t#{session_created}\t#{session_attached}\t#{session_windows}"],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return []
    if out.returncode != 0:
        return []  # covers "no server running"
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4 or not TMUX_NAME_RE.match(parts[0]):
            continue
        created = int(parts[1]) if parts[1].isdigit() else 0
        rows.append({
            "name": parts[0],
            "created": created,
            "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(created)) if created else "",
            "attached": parts[2] not in ("", "0"),
            "windows": parts[3],
        })
    rows.sort(key=lambda r: r["created"], reverse=True)
    return rows


def list_workdirs(root: str | None = None) -> list[str]:
    root = root or config.WORKSPACE_DIR
    dirs = ["~"]
    if os.path.isdir(root):
        dirs += sorted(
            d for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d)) and not d.startswith(".")
        )
    return dirs
