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


S1 = "11111111-aaaa-bbbb-cccc-dddddddddddd"
S2 = "22222222-aaaa-bbbb-cccc-dddddddddddd"


def _write_transcript(slugdir, uuid, messages, mtime=None):
    slugdir.mkdir(parents=True, exist_ok=True)
    path = slugdir / f"{uuid}.jsonl"
    path.write_text("\n".join(json.dumps(m) for m in messages) + "\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _msg(role, text):
    return {"type": role, "message": {"content": [{"type": "text", "text": text}]}}


@pytest.fixture
def search_archive(tmp_path):
    # host A / S1: two "login" messages (one also "oauth"), plus noise that
    # contains "kubernetes" but must never count: a tool_use block, a
    # '<'-prefixed message, and a Caveat: line.
    _write_transcript(
        tmp_path / "hostA" / "-Users-guillermo-workspace-app", S1,
        [
            _msg("user", "the login page is broken " + "x" * 200),
            _msg("assistant", "login login login — the oauth callback is the cause"),
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "input": {"command": "kubectl get pods -n kubernetes"}}]}},
            _msg("user", "<system-reminder>kubernetes</system-reminder>"),
            _msg("user", "Caveat: kubernetes mentioned here too"),
        ],
        mtime=2_000_000_000,
    )
    # host B: older copy of the SAME uuid with unique content — must not be scanned
    _write_transcript(
        tmp_path / "hostB" / "-Users-guillermo-workspace-app", S1,
        [_msg("user", "zebra crossing login")],
        mtime=1_000_000_000,
    )
    # host A / S2: one "login" match
    _write_transcript(
        tmp_path / "hostA" / "-Users-guillermo-workspace-web", S2,
        [_msg("user", "add LOGIN rate limiting")],
        mtime=1_500_000_000,
    )
    return tmp_path


def test_search_basic(search_archive):
    rows = sessions.search_claude(["login"], str(search_archive))
    assert [r["uuid"] for r in rows] == [S1, S2]     # 2 matches > 1 match
    r = rows[0]
    assert r["host"] == "hostA" and r["matches"] == 2 and r["project"] == "app"
    assert "login" in rows[0]["snippets"][0]


def test_search_and_across_messages(search_archive):
    # "login" and "oauth" never share a message in S1 — AND is session-level
    rows = sessions.search_claude(["login", "oauth"], str(search_archive))
    assert [r["uuid"] for r in rows] == [S1]
    assert sessions.search_claude(["login", "nonexistent"], str(search_archive)) == []


def test_search_skips_noise_and_tools(search_archive):
    # "kubernetes" exists only in a tool_use block, a '<'-message, and a Caveat:
    assert sessions.search_claude(["kubernetes"], str(search_archive)) == []


def test_search_dedup_newest_host(search_archive):
    rows = sessions.search_claude(["login"], str(search_archive))
    assert rows[0]["host"] == "hostA"
    # content unique to the older hostB copy is not searchable
    assert sessions.search_claude(["zebra"], str(search_archive)) == []


def test_search_case_insensitive(search_archive):
    assert sessions.search_claude(["LOGIN"], str(search_archive))
    assert sessions.search_claude(["rate"], str(search_archive))[0]["uuid"] == S2


def test_search_repeats_count_once(search_archive):
    # "login login login" in one message still counts that message once
    rows = sessions.search_claude(["login"], str(search_archive))
    assert rows[0]["matches"] == 2


def test_search_snippet_ellipsis(search_archive):
    rows = sessions.search_claude(["broken"], str(search_archive))
    snip = rows[0]["snippets"][0]
    assert snip.endswith("…") and "  " not in snip


def test_search_oversized_line_skipped(search_archive, monkeypatch):
    # guard sits between the ~120-byte oauth line and the ~300-byte broken line
    monkeypatch.setattr(sessions, "_MAX_SEARCH_LINE", 160)
    assert sessions.search_claude(["broken"], str(search_archive)) == []
    # short lines still match
    assert sessions.search_claude(["oauth"], str(search_archive))


def test_search_snippet_is_plain_text(tmp_path):
    _write_transcript(
        tmp_path / "hostA" / "-Users-guillermo-workspace-x", S1,
        [_msg("user", "beware <script>alert(1)</script> zulu")],
    )
    rows = sessions.search_claude(["zulu"], str(tmp_path))
    # server returns raw text; escaping is the UI's job
    assert "<script>" in rows[0]["snippets"][0]


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
