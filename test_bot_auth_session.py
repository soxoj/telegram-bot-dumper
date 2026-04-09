"""Tests for bot_auth session file handling.

Validates that bot_auth does not crash when the bot directory already
exists but contains no .session file (the bug from GitHub issue
'weird bug').
"""
import os
import shutil
import tempfile
import pytest

from dumper import bot_auth


@pytest.fixture(autouse=True)
def use_tmp_dir(monkeypatch, tmp_path):
    """Run each test inside an isolated temporary directory."""
    monkeypatch.chdir(tmp_path)


@pytest.mark.asyncio
async def test_bot_auth_missing_session_file_no_crash(monkeypatch):
    """bot_auth should not raise FileNotFoundError when the previous
    bot directory exists but has no .session file inside it."""
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
    assert open(new_session).read() == "session-data"
