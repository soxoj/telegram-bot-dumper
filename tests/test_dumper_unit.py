"""Unit tests for new logic added to dumper.py."""
import csv
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import dumper
from telethon.tl.types import (
    PeerUser, PeerChat, PeerChannel,
    MessageEmpty, MessageMediaPhoto,
)


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dumper, "base_path", str(tmp_path))
    monkeypatch.setattr(dumper, "all_chats", {})
    monkeypatch.setattr(dumper, "all_users", {})
    monkeypatch.setattr(dumper, "messages_by_chat", {})
    monkeypatch.setattr(dumper, "NO_PHOTOS", False)
    monkeypatch.setattr(dumper, "USERS_CSV", False)
    monkeypatch.setattr(dumper, "NO_MEDIA", False)
    monkeypatch.setattr(dumper, "NO_HISTORY", False)
    monkeypatch.setattr(dumper, "HISTORY_DUMP_STEP", 200)
    yield


class FakeBot:
    """Awaitable callable returning a fixed response. Stand-in for TelegramClient."""
    def __init__(self, response=None, id="999"):
        self.response = response
        self.id = id
        self.calls = []

    async def __call__(self, request):
        self.calls.append(request)
        return self.response


# ---------- chat_display_name ----------

def test_chat_display_name_user_with_username():
    user = SimpleNamespace(first_name="Ivan", last_name="Petrov", username="ivanp")
    assert dumper.chat_display_name(user) == "Ivan Petrov (@ivanp)"


def test_chat_display_name_user_no_username():
    user = SimpleNamespace(first_name="Ivan", last_name=None, username=None)
    assert dumper.chat_display_name(user) == "Ivan"


def test_chat_display_name_group_no_username():
    group = SimpleNamespace(title="My Group", username=None)
    assert dumper.chat_display_name(group) == '"My Group"'


def test_chat_display_name_channel_with_username():
    chan = SimpleNamespace(title="News", username="news")
    assert dumper.chat_display_name(chan) == '"News" (@news)'


def test_chat_display_name_anonymous_user_with_username_only():
    obj = SimpleNamespace(first_name=None, last_name=None, username="solo")
    assert dumper.chat_display_name(obj) == "@solo"


def test_chat_display_name_unknown():
    assert dumper.chat_display_name(SimpleNamespace()) == "?"


# ---------- get_chat_id ----------

def _msg(peer_id, from_id=None):
    return SimpleNamespace(peer_id=peer_id, from_id=from_id, to_id=None)


def test_get_chat_id_peer_user():
    m = _msg(PeerUser(user_id=42))
    assert dumper.get_chat_id(m, bot_id=999) == "42"


def test_get_chat_id_peer_chat():
    m = _msg(PeerChat(chat_id=777), from_id=PeerUser(user_id=42))
    assert dumper.get_chat_id(m, bot_id=999) == "777"


def test_get_chat_id_peer_channel():
    m = _msg(PeerChannel(channel_id=12345), from_id=PeerUser(user_id=42))
    assert dumper.get_chat_id(m, bot_id=999) == "12345"


# ---------- get_from_id ----------

def test_get_from_id_pm_incoming():
    m = _msg(PeerUser(user_id=42), from_id=PeerUser(user_id=42))
    assert dumper.get_from_id(m, bot_id=999) == "42"


def test_get_from_id_pm_outgoing_from_bot():
    m = _msg(PeerUser(user_id=42), from_id=PeerUser(user_id=999))
    assert dumper.get_from_id(m, bot_id=999) == "999"


def test_get_from_id_basic_group():
    m = _msg(PeerChat(chat_id=777), from_id=PeerUser(user_id=42))
    assert dumper.get_from_id(m, bot_id=999) == "42"


def test_get_from_id_supergroup():
    m = _msg(PeerChannel(channel_id=12345), from_id=PeerUser(user_id=42))
    assert dumper.get_from_id(m, bot_id=999) == "42"


# ---------- append_user_csv ----------

def _user_stub(**overrides):
    base = dict(id=1, username="u", first_name="F", last_name="L",
                phone="+1", lang_code="en", bot=False, premium=False,
                verified=False, scam=False, fake=False)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_append_user_csv_creates_with_header(tmp_path):
    dumper.append_user_csv(_user_stub(id=42, username="alice"))
    rows = list(csv.DictReader((tmp_path / "users.csv").open()))
    assert len(rows) == 1
    assert rows[0]["id"] == "42"
    assert rows[0]["username"] == "alice"


def test_append_user_csv_appends_no_duplicate_header(tmp_path):
    dumper.append_user_csv(_user_stub(id=1, username="a"))
    dumper.append_user_csv(_user_stub(id=2, username="b"))
    rows = list(csv.DictReader((tmp_path / "users.csv").open()))
    assert [r["id"] for r in rows] == ["1", "2"]


# ---------- save_user_info ----------

def test_save_user_info_users_csv_skips_json_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dumper, "USERS_CSV", True)
    dumper.save_user_info(_user_stub(id=42))
    assert (tmp_path / "users.csv").exists()
    assert not (tmp_path / "42").exists()


def test_save_user_info_default_writes_json_dir(tmp_path):
    user = _user_stub(id=42)
    user.to_dict = lambda: {"id": 42, "username": "u"}
    dumper.save_user_info(user)
    assert (tmp_path / "42").is_dir()
    assert (tmp_path / "42" / "42.json").exists()
    assert not (tmp_path / "users.csv").exists()


# ---------- save_user_photos NO_PHOTOS ----------

@pytest.mark.asyncio
async def test_save_user_photos_no_photos_skips_api(monkeypatch):
    monkeypatch.setattr(dumper, "NO_PHOTOS", True)
    bot = FakeBot()
    await dumper.save_user_photos(bot, _user_stub(id=42))
    assert bot.calls == []


# ---------- save_chats_text_history ----------

def test_save_chats_text_history_no_history(monkeypatch, tmp_path):
    monkeypatch.setattr(dumper, "NO_HISTORY", True)
    monkeypatch.setattr(dumper, "messages_by_chat",
                        {"100": {"buf": ["[1][1][...] hi"], "history": []}})
    dumper.save_chats_text_history()
    assert list(tmp_path.iterdir()) == []


def test_save_chats_text_history_writes_default(monkeypatch, tmp_path):
    monkeypatch.setattr(dumper, "messages_by_chat",
                        {"100": {"buf": ["a", "b"], "history": []}})
    dumper.save_chats_text_history()
    p = tmp_path / "100" / "100_history.txt"
    assert p.read_text() == "a\nb\n"


def test_save_chats_text_history_skips_empty_buf(monkeypatch, tmp_path):
    monkeypatch.setattr(dumper, "messages_by_chat",
                        {"100": {"buf": [], "history": []}})
    dumper.save_chats_text_history()
    assert list(tmp_path.iterdir()) == []


# ---------- process_message text format ----------

def _message(message_id, from_peer, peer_id, text="hi"):
    return SimpleNamespace(
        id=message_id, from_id=from_peer, peer_id=peer_id, to_id=None,
        date="2026-04-01", message=text, action=None, media=None,
    )


@pytest.mark.asyncio
async def test_process_message_pm_incoming_format(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=42), PeerUser(user_id=42), text="hello")
    await dumper.process_message(FakeBot(), m)
    out = capsys.readouterr().out
    assert "[5][42][2026-04-01] hello" in out


@pytest.mark.asyncio
async def test_process_message_pm_outgoing_format(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=999), PeerUser(user_id=42), text="reply")
    await dumper.process_message(FakeBot(), m)
    out = capsys.readouterr().out
    assert "[5][999][to:42][2026-04-01] reply" in out


@pytest.mark.asyncio
async def test_process_message_basic_group_format(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=42), PeerChat(chat_id=777), text="ho")
    await dumper.process_message(FakeBot(), m)
    out = capsys.readouterr().out
    assert "[5][from:42][group:777][2026-04-01] ho" in out


@pytest.mark.asyncio
async def test_process_message_supergroup_format(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=42), PeerChannel(channel_id=8888), text="x")
    await dumper.process_message(FakeBot(), m)
    out = capsys.readouterr().out
    assert "[5][from:42][group:8888][2026-04-01] x" in out


# ---------- process_message NO_HISTORY ----------

@pytest.mark.asyncio
async def test_process_message_no_history_skips_buffer(monkeypatch):
    monkeypatch.setattr(dumper, "NO_HISTORY", True)
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=42), PeerUser(user_id=42))
    await dumper.process_message(FakeBot(), m)
    assert dumper.messages_by_chat == {}


@pytest.mark.asyncio
async def test_process_message_default_appends_buffer(monkeypatch):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=42), PeerUser(user_id=42), text="hi")
    await dumper.process_message(FakeBot(), m)
    assert "42" in dumper.messages_by_chat
    assert any("hi" in line for line in dumper.messages_by_chat["42"]["buf"])


# ---------- process_message NO_MEDIA ----------

@pytest.mark.asyncio
async def test_process_message_no_media_keeps_text(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "NO_MEDIA", True)
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    save_calls = []
    async def fake_save(*a, **kw): save_calls.append(a)
    monkeypatch.setattr(dumper, "save_media_photo", fake_save)

    m = _message(5, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaPhoto(photo=SimpleNamespace(id=12345))
    await dumper.process_message(FakeBot(), m)

    assert save_calls == []
    assert "Photo: media/12345.jpg" in capsys.readouterr().out


# ---------- process_message empty-counter print contract ----------

@pytest.mark.asyncio
async def test_process_message_prints_empty_counter_on_transition(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=42), PeerUser(user_id=42), text="ok")
    await dumper.process_message(FakeBot(), m, empty_message_counter=29)
    out = capsys.readouterr().out
    assert out.count("Empty messages x29") == 1


@pytest.mark.asyncio
async def test_process_message_no_empty_print_when_counter_zero(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(5, PeerUser(user_id=42), PeerUser(user_id=42), text="ok")
    await dumper.process_message(FakeBot(), m, empty_message_counter=0)
    out = capsys.readouterr().out
    assert "Empty messages" not in out


# ---------- process_message discover_user paths ----------

@pytest.mark.asyncio
async def test_process_message_resolves_outgoing_bot_recipient(monkeypatch):
    user_obj = _user_stub(id=42)
    user_obj.to_dict = lambda: {"id": 42}
    bot = FakeBot(response=SimpleNamespace(users=[user_obj]))
    resolved = []
    monkeypatch.setattr(dumper, "save_user_info", lambda u: resolved.append(("save", u.id)))
    monkeypatch.setattr(dumper, "print_user_info", lambda u: None)
    monkeypatch.setattr(dumper, "remove_old_text_history", lambda uid: None)
    async def fake_photos(b, u): resolved.append(("photos", u.id))
    monkeypatch.setattr(dumper, "save_user_photos", fake_photos)

    # Outgoing bot → user (user not yet in all_users).
    m = _message(5, PeerUser(user_id=999), PeerUser(user_id=42), text="hi user")
    await dumper.process_message(bot, m)

    assert ("save", 42) in resolved
    assert ("photos", 42) in resolved
    assert "42" in dumper.all_users


@pytest.mark.asyncio
async def test_process_message_does_not_resolve_known_user(monkeypatch):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    bot = FakeBot()
    m = _message(5, PeerUser(user_id=42), PeerUser(user_id=42))
    await dumper.process_message(bot, m)
    assert bot.calls == []  # no GetFullUserRequest issued


# ---------- discover_user ----------

@pytest.mark.asyncio
async def test_discover_user_resolves_and_caches(monkeypatch):
    user_obj = _user_stub(id=42)
    user_obj.to_dict = lambda: {"id": 42}
    bot = FakeBot(response=SimpleNamespace(users=[user_obj]))
    monkeypatch.setattr(dumper, "save_user_info", lambda u: None)
    monkeypatch.setattr(dumper, "print_user_info", lambda u: None)
    monkeypatch.setattr(dumper, "remove_old_text_history", lambda uid: None)
    async def noop(*a, **kw): pass
    monkeypatch.setattr(dumper, "save_user_photos", noop)

    await dumper.discover_user(bot, "42")
    assert "42" in dumper.all_users
    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_discover_user_skips_when_known(monkeypatch):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    bot = FakeBot()
    await dumper.discover_user(bot, "42")
    assert bot.calls == []


# ---------- probe_max_id ----------

@pytest.mark.asyncio
async def test_probe_max_id_returns_highest_real():
    real_ids = {1, 10, 100}
    candidates = [10 ** i for i in range(0, 10)]
    msgs = [SimpleNamespace(id=c) if c in real_ids else MessageEmpty(id=c, peer_id=None)
            for c in candidates]
    bot = FakeBot(response=SimpleNamespace(messages=msgs))
    assert await dumper.probe_max_id(bot) == 100


@pytest.mark.asyncio
async def test_probe_max_id_all_empty_returns_zero():
    candidates = [10 ** i for i in range(0, 10)]
    msgs = [MessageEmpty(id=c, peer_id=None) for c in candidates]
    bot = FakeBot(response=SimpleNamespace(messages=msgs))
    assert await dumper.probe_max_id(bot) == 0
