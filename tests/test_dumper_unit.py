"""Unit tests for new logic added to dumper.py."""
import csv
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import dumper
from telethon.tl.types import (
    PeerUser, PeerChat, PeerChannel,
    MessageEmpty, MessageMediaPhoto,
    MessageMediaPoll, MessageMediaVenue, MessageMediaDice, MessageMediaGame,
    MessageMediaInvoice, MessageMediaGeoLive, MessageMediaWebPage,
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
        self.downloaded_photos = []

    async def __call__(self, request):
        self.calls.append(request)
        return self.response

    async def download_profile_photo(self, entity, file=None):
        self.downloaded_photos.append((entity, file))
        return "fake_photo.jpg"



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

# ---------- save_chat_photo ----------
# NO_PHOTOS = True
@pytest.mark.asyncio
async def test_save_chat_photo_no_photos_skips_api(monkeypatch):
    monkeypatch.setattr(dumper, "NO_PHOTOS", True)
    bot = FakeBot()
    chat = SimpleNamespace(id=12345)
    await dumper.save_chat_photo(bot, chat)
    assert len(bot.downloaded_photos) == 0

# NO_PHOTOS = False
@pytest.mark.asyncio
async def test_save_chat_photo_works(monkeypatch):
    monkeypatch.setattr(dumper, "NO_PHOTOS", False)
    bot = FakeBot()
    chat = SimpleNamespace(id=12345)
    await dumper.save_chat_photo(bot, chat)
    assert len(bot.downloaded_photos) == 1

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


# ---------- process_message media descriptions ----------

@pytest.mark.asyncio
async def test_process_message_media_poll(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    poll = SimpleNamespace(
        question="Do you prefer Python or Go?",
        answers=["Python", "Go", "Both"],
    )
    m = _message(10, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaPoll(poll=poll, results=None)
    await dumper.process_message(FakeBot(), m)
    assert 'Poll: "Do you prefer Python or Go?" [3 options]' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_poll_text_with_entities(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    q_obj = SimpleNamespace(text="Single choice?")
    poll = SimpleNamespace(question=q_obj, answers=[SimpleNamespace(text="Yes")])
    m = _message(11, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaPoll(poll=poll, results=None)
    await dumper.process_message(FakeBot(), m)
    assert 'Poll: "Single choice?" [1 option]' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_venue(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(12, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaVenue(
        geo=SimpleNamespace(lat=40.785091, long=-73.968285),
        title="Central Park",
        address="New York, NY",
        provider="foursquare",
        venue_id="123",
        venue_type="park",
    )
    await dumper.process_message(FakeBot(), m)
    assert "Venue: Central Park, New York, NY" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_dice(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(13, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaDice(value=6, emoticon="🎲")
    await dumper.process_message(FakeBot(), m)
    assert "Dice: 🎲 6" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_game(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(14, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaGame(game=SimpleNamespace(title="Corsairs"))
    await dumper.process_message(FakeBot(), m)
    assert "Game: Corsairs" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_invoice(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(15, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaInvoice(
        title="Donation",
        description="Support dev",
        currency="USD",
        total_amount=500,
        start_param="donate",
    )
    await dumper.process_message(FakeBot(), m)
    assert "Invoice: Donation (500 USD)" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_geo_live(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(16, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaGeoLive(
        geo=SimpleNamespace(long=37.6176, lat=55.7558),
        period=900,
    )
    await dumper.process_message(FakeBot(), m)
    assert "Live geoposition: 37.6176, 55.7558 (period: 900s)" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_webpage(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(17, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaWebPage(
        webpage=SimpleNamespace(title="Example Domain", url="https://example.com")
    )
    await dumper.process_message(FakeBot(), m)
    assert "WebPage: Example Domain (https://example.com)" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_venue_partial(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(18, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaVenue(
        geo=None,
        title="Eiffel Tower",
        address="",
        provider="",
        venue_id="",
        venue_type="",
    )
    await dumper.process_message(FakeBot(), m)
    assert "Venue: Eiffel Tower" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_dice_emoticon_only(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(19, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaDice(value=None, emoticon="🎯")
    await dumper.process_message(FakeBot(), m)
    assert "Dice: 🎯" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_process_message_media_webpage_url_only(monkeypatch, capsys):
    monkeypatch.setattr(dumper, "all_users", {"42": object()})
    m = _message(20, PeerUser(user_id=42), PeerUser(user_id=42), text="")
    m.media = MessageMediaWebPage(
        webpage=SimpleNamespace(title="", url="https://example.org")
    )
    await dumper.process_message(FakeBot(), m)
    assert "WebPage: https://example.org" in capsys.readouterr().out


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


# --- service messages (#33) -------------------------------------------------

from telethon.tl.types import (  # noqa: E402
    MessageActionBoostApply, MessageActionChatAddUser, MessageActionChatCreate,
    MessageActionChatDeletePhoto, MessageActionChatDeleteUser, MessageActionChatEditTitle,
    MessageActionChatJoinedByLink, MessageActionChatMigrateTo, MessageActionCustomAction,
    MessageActionGroupCall, MessageActionHistoryClear, MessageActionPhoneCall,
    MessageActionPinMessage,
)


@pytest.mark.parametrize("action, from_id, reply_to_msg_id, expected", [
    (MessageActionChatCreate(title="Team", users=[1, 2]), None, None, 'Created the group "Team"'),
    (MessageActionChatEditTitle(title="New name"), None, None, 'Changed the group title to "New name"'),
    (MessageActionChatDeletePhoto(), None, None, 'Removed the group photo'),
    (MessageActionChatAddUser(users=[42]), 42, None, 'Joined the group'),
    (MessageActionChatAddUser(users=[7, 8]), 42, None, 'Added 7, 8 to the group'),
    (MessageActionChatJoinedByLink(inviter_id=5), 42, None, 'Joined the group via invite link'),
    (MessageActionChatDeleteUser(user_id=42), 42, None, 'Left the group'),
    (MessageActionChatDeleteUser(user_id=7), 42, None, 'Removed 7 from the group'),
    (MessageActionChatMigrateTo(channel_id=100), None, None, 'Upgraded the group to a supergroup'),
    (MessageActionPinMessage(), None, 17, 'Pinned message 17'),
    (MessageActionPinMessage(), None, None, 'Pinned a message'),
    (MessageActionHistoryClear(), None, None, 'Cleared the chat history'),
    (MessageActionCustomAction(message="Bot says hi"), None, None, 'Bot says hi'),
    (MessageActionPhoneCall(call_id=1, duration=65), None, None, 'Phone call (65 s)'),
    (MessageActionGroupCall(call=None, duration=None), None, None, 'Started a group call'),
])
def test_describe_service_action(action, from_id, reply_to_msg_id, expected):
    assert dumper.describe_service_action(
        action, from_id=from_id, reply_to_msg_id=reply_to_msg_id,
    ) == expected


def test_describe_service_action_keeps_repr_for_unmapped_types():
    """An action without a description keeps what the history recorded before."""
    action = MessageActionBoostApply(boosts=2)
    assert dumper.describe_service_action(action) == str(action)


def _service_message(action, reply_to=None):
    """A service message in a basic group, sent by user 42."""
    return SimpleNamespace(
        id=5, peer_id=PeerChat(chat_id=100), from_id=PeerUser(user_id=42), to_id=None,
        date="2026-09-11 10:00:00", media=None, message="", action=action, reply_to=reply_to,
    )


def _history_line():
    (chat,) = dumper.messages_by_chat.values()
    return chat["buf"][-1]


@pytest.mark.asyncio
async def test_service_message_lands_in_history_as_readable_text():
    """Goes through the real get_from_id, so the self-join check sees the actual sender."""
    await dumper.process_message(FakeBot(), _service_message(MessageActionChatAddUser(users=[42])))

    line = _history_line()
    assert line.endswith("Joined the group")
    assert "MessageActionChatAddUser" not in line
    assert line.startswith("[5][from:42]")


@pytest.mark.asyncio
async def test_pinned_service_message_names_the_pinned_message():
    reply_to = SimpleNamespace(reply_to_msg_id=17)
    await dumper.process_message(FakeBot(), _service_message(MessageActionPinMessage(), reply_to))

    assert _history_line().endswith("Pinned message 17")

# ---------- safe_process_message / dump resilience (#50) ----------

@pytest.mark.asyncio
async def test_history_dump_skips_one_bad_message(monkeypatch, capsys):
    """One parse failure must not abort the rest of the batch."""
    monkeypatch.setattr(dumper, "all_users", {"42": object(), "7": object()})

    good_a = _message(1, PeerUser(user_id=42), PeerUser(user_id=42), text="first")
    bad = _message(2, PeerUser(user_id=42), PeerUser(user_id=42), text="boom")
    good_b = _message(3, PeerUser(user_id=7), PeerUser(user_id=7), text="third")

    real = dumper.process_message

    async def exploding(bot, m, empty_message_counter=0):
        if getattr(m, "id", None) == 2:
            raise AttributeError("'ReplyKeyboardHide' object has no attribute 'rows'")
        return await real(bot, m, empty_message_counter)

    monkeypatch.setattr(dumper, "process_message", exploding)

    bot = FakeBot(response=SimpleNamespace(messages=[good_a, bad, good_b]))
    await dumper.get_chat_history(bot, from_id=4, to_id=1)

    out = capsys.readouterr().out
    assert "Failed to process message id=2" in out
    assert "chat_id=" in out
    assert "ReplyKeyboardHide" in out or "rows" in out
    hist_42 = dumper.messages_by_chat.get("42", {}).get("history", [])
    hist_7 = dumper.messages_by_chat.get("7", {}).get("history", [])
    assert any("first" in line for line in hist_42)
    assert any("third" in line for line in hist_7)
    assert not any("boom" in line for line in hist_42 + hist_7)


@pytest.mark.asyncio
async def test_safe_process_message_rethrows_cancelled_error(monkeypatch):
    import asyncio as aio

    async def boom(bot, m, empty_message_counter=0):
        raise aio.CancelledError()

    monkeypatch.setattr(dumper, "process_message", boom)
    with pytest.raises(aio.CancelledError):
        await dumper.safe_process_message(FakeBot(), SimpleNamespace(id=9, chat_id=1))
