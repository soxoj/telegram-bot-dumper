"""Tests for bot_auth session file handling.

Validates that bot_auth does not crash when the bot directory already
exists but contains no .session file (the bug from GitHub issue
'weird bug').
"""
import os
import shutil
import tempfile
from types import SimpleNamespace

import pytest

from telethon.errors.rpcerrorlist import AccessTokenInvalidError

from dumper import bot_auth, main


@pytest.fixture(autouse=True)
def use_tmp_dir(monkeypatch, tmp_path):
    """Run each test inside an isolated temporary directory."""
    monkeypatch.chdir(tmp_path)


@pytest.mark.asyncio
async def test_bot_auth_missing_session_file_no_crash(monkeypatch):
    """bot_auth should not raise FileNotFoundError when the previous
    bot directory exists but has no .session file inside it."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abc123hash")
    bot_id = "123456789"
    fake_token = f"{bot_id}:AAFakeTokenValue"

    # Pre-create the bot directory WITHOUT a session file to simulate
    # a previous failed run.
    os.mkdir(bot_id)

    # Patch TelegramClient so we don't actually connect to Telegram.
    # We only need to verify the file-handling code before TelegramClient
    # is instantiated.
    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise KeyboardInterrupt("stop before real network call")

    monkeypatch.setattr("dumper.TelegramClient", _FakeClient)

    with pytest.raises(KeyboardInterrupt):
        await bot_auth(fake_token)

    # The old directory should have been renamed, and a new one created.
    assert os.path.isdir(bot_id)


@pytest.mark.asyncio
async def test_bot_auth_existing_session_file_is_copied(monkeypatch):
    """When a .session file exists in the old directory it should be
    copied into the freshly created directory."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abc123hash")
    bot_id = "987654321"
    fake_token = f"{bot_id}:AAFakeTokenValue"

    # Pre-create the bot directory WITH a session file.
    os.mkdir(bot_id)
    session_path = os.path.join(bot_id, f"{bot_id}.session")
    with open(session_path, "w") as f:
        f.write("session-data")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise KeyboardInterrupt("stop before real network call")

    monkeypatch.setattr("dumper.TelegramClient", _FakeClient)

    with pytest.raises(KeyboardInterrupt):
        await bot_auth(fake_token)

    # The session file should have been copied to the new directory.
    new_session = os.path.join(bot_id, f"{bot_id}.session")
    assert os.path.isfile(new_session)
    with open(new_session) as f:
        assert f.read() == "session-data"


@pytest.mark.asyncio
async def test_bot_auth_with_custom_output_dir(monkeypatch):
    """bot_auth with output_dir should create output_dir/bot_id."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abc123hash")
    bot_id = "987654321"
    fake_token = f"{bot_id}:AAFakeTokenValue"
    custom_output = "custom_dumps"
    custom_path = os.path.join(custom_output, bot_id)

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise KeyboardInterrupt("stop before real network call")

    monkeypatch.setattr("dumper.TelegramClient", _FakeClient)

    with pytest.raises(KeyboardInterrupt):
        await bot_auth(fake_token, output_dir=custom_output)

    assert os.path.isdir(os.path.join(custom_output, bot_id))
    assert not os.path.exists(bot_id)

@pytest.mark.asyncio
async def test_bot_auth_custom_output_dir_rotation(monkeypatch):
    """When previous dump exists in output_dir, it should be rotated and session preserved."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abc123hash")
    bot_id = "987654321"
    fake_token = f"{bot_id}:AAFakeTokenValue"
    custom_output = "custom_dumps"
    custom_path = os.path.join(custom_output, bot_id)

    os.makedirs(custom_path, exist_ok=True)
    session_path = os.path.join(custom_path, f"{bot_id}.session")
    with open(session_path, "w") as f:
        f.write("session-data")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise KeyboardInterrupt("stop before real network call")

    monkeypatch.setattr("dumper.TelegramClient", _FakeClient)

    with pytest.raises(KeyboardInterrupt):
        await bot_auth(fake_token, output_dir=custom_output)

    entries = os.listdir(custom_output)
    assert len(entries) == 2

    new_session = os.path.join(custom_path, f"{bot_id}.session")
    assert os.path.isfile(new_session)
    with open(new_session) as f:
        assert f.read() == "session-data"


@pytest.mark.asyncio
async def test_bot_auth_missing_api_creds_exits_friendly(monkeypatch, capsys):
    """Missing API_ID/API_HASH prints one line and exits 1 without touching disk."""
    monkeypatch.setattr("dumper.API_ID", 0)
    monkeypatch.setattr("dumper.API_HASH", "")
    bot_id = "123456789"
    fake_token = f"{bot_id}:AAFakeTokenValue"

    with pytest.raises(SystemExit) as exc_info:
        await bot_auth(fake_token)

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "API_ID and API_HASH are not set" in out
    assert "Traceback" not in out
    assert not os.path.exists(bot_id)


@pytest.mark.asyncio
async def test_bot_auth_invalid_token_exits_friendly_and_cleans(monkeypatch, capsys):
    """Invalid token prints one line, exits 1, and removes the just-created folder."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abc123hash")
    bot_id = "123456789"
    fake_token = f"{bot_id}:AAFakeTokenValue"

    class _FakeInvalidClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise AccessTokenInvalidError(request=None)

    monkeypatch.setattr("dumper.TelegramClient", _FakeInvalidClient)

    with pytest.raises(SystemExit) as exc_info:
        await bot_auth(fake_token)

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Telegram rejected the token (invalid or revoked)." in out
    assert "Traceback" not in out
    assert not os.path.exists(bot_id)


@pytest.mark.asyncio
async def test_bot_auth_invalid_token_preserves_rotated_dump(monkeypatch, capsys):
    """Cleanup removes only the fresh folder; the rotated previous dump is kept."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abc123hash")
    bot_id = "123456789"
    fake_token = f"{bot_id}:AAFakeTokenValue"

    os.mkdir(bot_id)
    sentinel = os.path.join(bot_id, "keepme.txt")
    with open(sentinel, "w") as f:
        f.write("previous-dump")

    class _FakeInvalidClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise AccessTokenInvalidError(request=None)

    monkeypatch.setattr("dumper.TelegramClient", _FakeInvalidClient)

    with pytest.raises(SystemExit) as exc_info:
        await bot_auth(fake_token)

    assert exc_info.value.code == 1
    assert "Telegram rejected the token (invalid or revoked)." in capsys.readouterr().out
    # Fresh folder is gone; rotated previous dump (bot_id_<timestamp>) keeps its file.
    assert not os.path.exists(bot_id)
    rotated = [e for e in os.listdir(".") if e.startswith(f"{bot_id}_")]
    assert len(rotated) == 1
    assert os.path.isfile(os.path.join(rotated[0], "keepme.txt"))


@pytest.mark.asyncio
async def test_main_no_token_no_terminal_exits_friendly(monkeypatch, capsys):
    """No --token with no terminal prints one line and exits 1 (no traceback)."""
    args = SimpleNamespace(token=None, tor=False)

    def _no_terminal(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", _no_terminal)

    with pytest.raises(SystemExit) as exc_info:
        await main(args)

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "No token given: pass --token, or run in a terminal to type it." in out
    assert "Traceback" not in out
