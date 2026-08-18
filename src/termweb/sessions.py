"""Session listings, read from the hostPath mounts (claude archive, codex
rollouts, workspace) plus one ssh round-trip for live tmux sessions.

The claude listing is a port of the embedded Python block in the
claude-sessions CLI (`cmd_list`), emitting dicts instead of fixed-width text.
"""

import json
import os
import re
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


# Lines bigger than this are tool dumps (excluded from search anyway); skipping
# them caps the transient .lower() copy under the pod's 512Mi memory limit.
_MAX_SEARCH_LINE = 16 * 1024 * 1024


def _snippet(text: str, low: str, term: str, ctx: int = 60) -> str:
    i = low.find(term)
    s, e = max(0, i - ctx), min(len(text), i + len(term) + ctx)
    out = " ".join(text[s:e].split())
    return ("…" if s else "") + out + ("…" if e < len(text) else "")


def search_claude(terms: list[str], root: str | None = None,
                  limit: int = 50) -> list[dict]:
    """Full-text search of archived transcripts. Case-insensitive; all terms
    must appear somewhere in a session's conversation text (user + assistant
    text blocks; '<'/'Caveat:' noise and tool dumps excluded), possibly in
    different messages. One row per uuid — newest copy across hosts wins
    (path tie-break). Ranked by matching-message count (once per message),
    then recency. Streaming binary scan with an any-term raw prefilter before
    json.loads — same algorithm as the CLI's cmd_search."""
    root = root or config.CLAUDE_ARCHIVE_DIR
    terms = [t.lower() for t in terms]
    terms_b = [t.encode() for t in terms]
    if not terms or not os.path.isdir(root):
        return []

    newest: dict[str, tuple[float, str, str, str, int]] = {}
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
                cur = newest.get(f[:-6])
                if cur is None or (st.st_mtime, path) > (cur[0], cur[3]):
                    newest[f[:-6]] = (st.st_mtime, host, slug, path, st.st_size)

    rows = []
    for uuid, (mt, host, slug, path, size) in newest.items():
        found: set[str] = set()
        count, snips = 0, []
        try:
            with open(path, "rb") as fh:
                for raw in fh:
                    if len(raw) > _MAX_SEARCH_LINE:
                        continue
                    low = raw.lower()
                    if not any(tb in low for tb in terms_b):
                        continue
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    if obj.get("type") not in ("user", "assistant"):
                        continue
                    msg = obj.get("message") or {}
                    c = msg.get("content")
                    if isinstance(c, list):
                        c = "\n".join(p.get("text", "") for p in c
                                      if isinstance(p, dict) and p.get("type") == "text")
                    if not isinstance(c, str):
                        continue
                    c = c.strip()
                    if not c or c.startswith("<") or c.startswith("Caveat:"):
                        continue
                    cl = c.lower()
                    hit = [t for t in terms if t in cl]
                    if not hit:
                        continue
                    count += 1  # once per message, however many occurrences
                    found.update(hit)
                    if len(snips) < 3:
                        snips.append(_snippet(c, cl, hit[0]))
        except OSError:
            continue
        if count and found == set(terms):
            rows.append({
                "mtime": mt,
                "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(mt)),
                "host": host,
                "slug": slug,
                "project": slug.split("-")[-1] or slug,
                "uuid": uuid,
                "kb": size // 1024,
                "matches": count,
                "snippets": snips,
            })
    rows.sort(key=lambda r: (r["matches"], r["mtime"]), reverse=True)
    return rows[:limit]


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


def claude_cwd(path: str) -> str:
    """First recorded cwd in a claude transcript."""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj.get("cwd"), str):
                    return obj["cwd"]
    except OSError:
        pass
    return ""


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


def list_workdirs(root: str | None = None) -> list[str]:
    root = root or config.WORKSPACE_DIR
    dirs = ["~"]
    if os.path.isdir(root):
        dirs += sorted(
            d for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d)) and not d.startswith(".")
        )
    return dirs
