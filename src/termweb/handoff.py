"""Cross-agent handoff: digest a Claude or Codex transcript into a markdown file
the *other* agent reads as its starting context. Tool calls/results are dropped —
the digest is the conversation narrative; the repo state carries the rest.
"""

import json

MAX_DIGEST_BYTES = 100_000


def _claude_turns(path: str):
    """Yield (role, text) turns from a claude-code transcript jsonl."""
    cwd = ""
    turns = []
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not cwd and isinstance(obj.get("cwd"), str):
                cwd = obj["cwd"]
            role = obj.get("type")
            if role not in ("user", "assistant"):
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
            turns.append((role, c))
    return cwd, turns


def _codex_turns(path: str):
    cwd = ""
    turns = []
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
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            text = "\n".join(
                p.get("text", "") for p in payload.get("content", [])
                if isinstance(p, dict) and p.get("type") in ("input_text", "output_text")
            ).strip()
            if not text or text.startswith("<") or (role == "user" and text.startswith("#")):
                continue
            turns.append((role, text))
    return cwd, turns


def build_digest(source_agent: str, path: str, remote_path: str) -> tuple[str, str]:
    """Return (recorded_cwd, markdown digest). `remote_path` is where the raw
    transcript lives on forge, noted in the footer for deeper digging."""
    cwd, turns = (_claude_turns if source_agent == "claude" else _codex_turns)(path)

    parts = [
        f"# Prior {source_agent} session — handoff digest\n",
        f"Working directory: `{cwd or 'unknown'}`\n",
    ]
    if turns:
        first_role, first_text = turns[0]
        parts.append(f"## Original task ({first_role})\n\n{first_text[:4000]}\n")

    # Tail-weighted: keep the most recent turns that fit the budget.
    budget = MAX_DIGEST_BYTES - sum(len(p) for p in parts) - 500
    tail: list[str] = []
    for role, text in reversed(turns[1:]):
        block = f"**{role}:**\n\n{text}\n"
        if budget - len(block) < 0:
            break
        budget -= len(block)
        tail.append(block)
    if tail:
        parts.append("## Conversation (most recent turns)\n")
        parts.extend(reversed(tail))

    parts.append(
        f"\n---\nRaw transcript on this machine: `{remote_path}` "
        f"(full detail incl. tool calls — read it if this digest isn't enough).\n"
    )
    return cwd, "\n".join(parts)
