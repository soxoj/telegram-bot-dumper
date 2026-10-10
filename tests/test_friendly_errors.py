"""Tests for friendly setup error messages (issue #62)."""
import os
from unittest.mock import patch

import pytest

import dumper


@pytest.mark.asyncio
async def test_missing_api_credentials(capsys, monkeypatch):
    """Missing API_ID/API_HASH should print a clear message and exit 1."""
    monkeypatch.setattr(dumper, "API_ID", 0)
    monkeypatch.setattr(dumper, "API_HASH", "")

    class Args:
        token = "123:fake"
        tor = False
        output = None

    with pytest.raises(SystemExit) as exc:
        await dumper.main(Args())
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "API_ID and API_HASH are not set" in captured.out
    assert "https://my.telegram.org" in captured.out


@pytest.mark.asyncio
async def test_invalid_token_cleans_up_and_exits(capsys, monkeypatch, tmp_path):
    """Invalid token should print friendly message, exit 1, and remove the new dump folder."""
    monkeypatch.setattr(dumper, "API_ID", 12345)
    monkeypatch.setattr(dumper, "API_HASH", "fakehash")

    bot_id = "987654321"
    fake_token = f"{bot_id}:AAFakeToken"

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise dumper.AccessTokenInvalidError(None)

    monkeypatch.setattr(dumper, "TelegramClient", _FakeClient)

    dump_path = tmp_path / bot_id
    assert not dump_path.exists()

    with pytest.raises(SystemExit) as exc:
        await dumper.bot_auth(fake_token, output_dir=str(tmp_path))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Telegram rejected the token" in captured.out
    assert not dump_path.exists(), "Newly created dump folder should be removed"


@pytest.mark.asyncio
async def test_no_token_eof(capsys, monkeypatch):
    """EOF when prompting for token should print clear message and exit 1."""
    monkeypatch.setattr(dumper, "API_ID", 12345)
    monkeypatch.setattr(dumper, "API_HASH", "fakehash")

    class Args:
        token = None
        tor = False
        output = None

    with patch("builtins.input", side_effect=EOFError):
        with pytest.raises(SystemExit) as exc:
            await dumper.main(Args())
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "No token given" in captured.out
