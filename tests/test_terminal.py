import os

os.environ.setdefault("SESSION_SECRET", "test-secret")

from termweb import terminal  # noqa: E402


def test_build_claude_command():
    cmd = terminal.build_remote_command(
        {"kind": "claude", "uuid": "11111111-2222-3333-4444-555555555555",
         "name": "cs-11111111"})
    assert cmd.startswith("/usr/bin/tmux new-session -A -s cs-11111111 ")
    assert "CLAUDE_SESSIONS_REMOTE=local" in cmd
    assert ".local/bin" in cmd
    assert "claude-sessions open 11111111-2222-3333-4444-555555555555" in cmd


def test_build_codex_command():
    cmd = terminal.build_remote_command(
        {"kind": "codex", "uuid": "01a001c7-5d47-7ac2-a767-0c12254fe3a6",
         "cwd": "/home/guillermo/workspace/demo", "name": "cx-01a001c7"})
    assert "codex resume 01a001c7" in cmd
    assert "cd /home/guillermo/workspace/demo ||" in cmd


def test_build_cross_command():
    cmd = terminal.build_remote_command(
        {"kind": "cross", "agent": "codex", "cwd": "/home/guillermo",
         "handoff": ".cache/term-web/handoff-11111111.md", "name": "xc-11111111"})
    assert "codex " in cmd
    assert "handoff-11111111.md" in cmd


def test_build_new_command():
    cmd = terminal.build_remote_command(
        {"kind": "new", "agent": "claude", "workdir": "demo",
         "name": "new-claude-demo-ab12"})
    assert 'cd "$HOME/workspace/demo"' in cmd


def test_ticket_roundtrip_and_one_time():
    target = {"kind": "attach", "name": "cs-11111111"}
    t = terminal.mint_ticket("g@kardol.us", target)
    assert terminal.redeem_ticket(t, "g@kardol.us") == target
    assert terminal.redeem_ticket(t, "g@kardol.us") is None  # one-time


def test_ticket_wrong_email():
    t = terminal.mint_ticket("g@kardol.us", {"kind": "attach", "name": "x"})
    assert terminal.redeem_ticket(t, "other@kardol.us") is None


def test_ticket_garbage():
    assert terminal.redeem_ticket("garbage", "g@kardol.us") is None
