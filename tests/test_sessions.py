import json
import os

import pytest

os.environ.setdefault("SESSION_SECRET", "test-secret")

from termweb import handoff, sessions  # noqa: E402


@pytest.fixture
def claude_archive(tmp_path):
    slugdir = tmp_path / "mbp14" / "-Users-guillermo-workspace-demo"
    slugdir.mkdir(parents=True)
    lines = [
        {"type": "summary", "summary": "irrelevant"},
        {"type": "user", "cwd": "/Users/guillermo/workspace/demo",
         "message": {"content": "<system-reminder>skip me</system-reminder>"}},
        {"type": "user", "cwd": "/Users/guillermo/workspace/demo",
         "message": {"content": "Caveat: skip this too"}},
        {"type": "user", "cwd": "/Users/guillermo/workspace/demo",
         "message": {"content": [{"type": "text", "text": "  fix the   login bug  "}]}},
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "Looking at auth.py now."}]}},
    ]
    path = slugdir / "11111111-2222-3333-4444-555555555555.jsonl"
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return tmp_path


def test_list_claude(claude_archive):
    rows = sessions.list_claude(str(claude_archive))
    assert len(rows) == 1
    r = rows[0]
    assert r["uuid"] == "11111111-2222-3333-4444-555555555555"
    assert r["host"] == "mbp14"
    assert r["project"] == "demo"
    assert r["preview"] == "fix the login bug"


def test_find_claude_transcript(claude_archive):
    assert sessions.find_claude_transcript(
        "11111111-2222-3333-4444-555555555555", str(claude_archive))
    assert sessions.find_claude_transcript(
        "99999999-2222-3333-4444-555555555555", str(claude_archive)) is None


@pytest.fixture
def codex_root(tmp_path):
    daydir = tmp_path / "2026" / "08" / "14"
    daydir.mkdir(parents=True)
    lines = [
        {"type": "session_meta",
         "payload": {"session_id": "01a001c7-5d47-7ac2-a767-0c12254fe3a6",
                     "cwd": "/Users/guillermo/workspace/demo"}},
        {"type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "<env>skip</env>"}]}},
        {"type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "add dark mode"}]}},
        {"type": "response_item",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "On it."}]}},
    ]
    path = daydir / "rollout-2026-08-14T19-37-17-01a001c7-5d47-7ac2-a767-0c12254fe3a6.jsonl"
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return tmp_path


def test_list_codex(codex_root):
    rows = sessions.list_codex(str(codex_root))
    assert len(rows) == 1
    r = rows[0]
    assert r["uuid"] == "01a001c7-5d47-7ac2-a767-0c12254fe3a6"
    assert r["cwd"] == "/Users/guillermo/workspace/demo"
    assert r["preview"] == "add dark mode"


def test_localize_cwd():
    assert sessions.localize_cwd("/Users/guillermo/workspace/demo") == "/home/guillermo/workspace/demo"
    assert sessions.localize_cwd("/home/guillermo/workspace/demo") == "/home/guillermo/workspace/demo"
    assert sessions.localize_cwd("") == "/home/guillermo"


def test_claude_digest(claude_archive):
    path = sessions.find_claude_transcript(
        "11111111-2222-3333-4444-555555555555", str(claude_archive))
    cwd, md = handoff.build_digest("claude", path, "/remote/path.jsonl")
    assert cwd == "/Users/guillermo/workspace/demo"
    assert "fix the   login bug" in md
    assert "Looking at auth.py now." in md
    assert "skip me" not in md
    assert "/remote/path.jsonl" in md


def test_codex_digest(codex_root):
    path = sessions.find_codex_rollout("01a001c7-5d47-7ac2-a767-0c12254fe3a6", str(codex_root))
    cwd, md = handoff.build_digest("codex", path, "/remote/rollout.jsonl")
    assert cwd == "/Users/guillermo/workspace/demo"
    assert "add dark mode" in md
    assert "On it." in md
    assert "<env>skip</env>" not in md
