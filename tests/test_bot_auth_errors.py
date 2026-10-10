"""Tests for the credential and token checks in bot_auth.

Covers the three failure modes from GitHub issue #62: missing API_ID/API_HASH,
a malformed token, and the interactive prompt that used to accept anything.
None of these reach the network; TelegramClient is patched out.
"""
import os
import sys

import pytest

import dumper
from dumper import ask_bot_token, bot_auth


GOOD_TOKEN = "123456789:AAFakeTokenValue"


@pytest.fixture(autouse=True)
def use_tmp_dir(monkeypatch, tmp_path):
    """Run each test inside an isolated temporary directory."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def fake_client(monkeypatch):
    """A TelegramClient stand-in that stops before any network call."""

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise KeyboardInterrupt("stop before real network call")

    monkeypatch.setattr("dumper.TelegramClient", _FakeClient)
    return _FakeClient


@pytest.mark.asyncio
async def test_missing_api_id_exits_with_error(monkeypatch, capsys):
    """Without API_ID or API_HASH, bot_auth should explain and exit 1."""
    monkeypatch.setattr("dumper.API_ID", 0)
    monkeypatch.setattr("dumper.API_HASH", "")

    with pytest.raises(SystemExit) as excinfo:
        await bot_auth(GOOD_TOKEN)

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "API_ID" in out and "API_HASH" in out


@pytest.mark.asyncio
async def test_missing_api_hash_only_exits_with_error(monkeypatch, capsys):
    """API_ID being set is not enough; both are required."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "")

    with pytest.raises(SystemExit) as excinfo:
        await bot_auth(GOOD_TOKEN)

    assert excinfo.value.code == 1
    assert "API_HASH" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_token_without_colon_exits_with_error(monkeypatch, capsys):
    """A token with no colon should be refused before TelegramClient is built."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abcdef0123456789")

    with pytest.raises(SystemExit) as excinfo:
        await bot_auth("not-a-real-token")

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "123456" in out


@pytest.mark.asyncio
async def test_revoked_token_exits_with_a_distinct_message(monkeypatch, capsys):
    """An expired token should say it was revoked, and exit 1."""
    from telethon.errors.rpcerrorlist import AccessTokenExpiredError

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise AccessTokenExpiredError(None)

    monkeypatch.setattr("dumper.TelegramClient", _FakeClient)
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abcdef0123456789")

    with pytest.raises(SystemExit) as excinfo:
        await bot_auth(GOOD_TOKEN)

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "expired" in out and "revoked" in out


@pytest.mark.asyncio
async def test_invalid_token_exits_with_a_distinct_message(monkeypatch, capsys):
    """An invalid token should be reported as a copy problem, not as revoked."""
    from telethon.errors.rpcerrorlist import AccessTokenInvalidError

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            raise AccessTokenInvalidError(None)

    monkeypatch.setattr("dumper.TelegramClient", _FakeClient)
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abcdef0123456789")

    with pytest.raises(SystemExit) as excinfo:
        await bot_auth(GOOD_TOKEN)

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "invalid" in out
    assert "revoked" not in out


@pytest.mark.asyncio
async def test_credentials_present_reaches_the_client(monkeypatch, fake_client):
    """With both variables set and a shaped token, the old path still runs."""
    monkeypatch.setattr("dumper.API_ID", 123456)
    monkeypatch.setattr("dumper.API_HASH", "abcdef0123456789")

    with pytest.raises(KeyboardInterrupt):
        await bot_auth(GOOD_TOKEN)

    assert os.path.isdir("123456789")


def test_ask_bot_token_accepts_a_well_formed_token(monkeypatch):
    """A token with a colon is returned, with surrounding whitespace removed."""
    monkeypatch.setattr("builtins.input", lambda *a: f"  {GOOD_TOKEN}  ")
    assert ask_bot_token() == GOOD_TOKEN


def test_ask_bot_token_reprompts_until_valid(monkeypatch, capsys):
    """A token with no colon is rejected and the prompt asks again."""
    answers = iter(["nope", "still-nope", GOOD_TOKEN])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    assert ask_bot_token() == GOOD_TOKEN
    out = capsys.readouterr().out
    assert out.count("wrong format") == 2


def test_ask_bot_token_exits_on_eof(monkeypatch, capsys):
    """Piped input that ends should exit 1 rather than loop forever."""
    def _raise(*a):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)

    with pytest.raises(SystemExit) as excinfo:
        ask_bot_token()

    assert excinfo.value.code == 1
    assert "--token" in capsys.readouterr().out
