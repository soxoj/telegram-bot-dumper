"""--listen-only end to end: the real main() and live handler, only the Telegram client is faked."""
import argparse
import os
from types import SimpleNamespace

import pytest
from telethon.tl.types import PeerUser

import dumper


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in ("all_chats", "all_users", "messages_by_chat"):
        monkeypatch.setattr(dumper, name, {})
    monkeypatch.setattr(dumper, "NO_HISTORY", False)
    # main() reaches bot_auth, which refuses to run without a credential pair
    # (so a missing one is named rather than left to Telethon). These tests are
    # about the live handler, not the credentials, so give it a pair.
    monkeypatch.setattr(dumper, "API_ID", 123456)
    monkeypatch.setattr(dumper, "API_HASH", "abcdef0123456789")


class FakeBot:
    def __init__(self):
        self.handlers = []

    def on(self, event):
        def deco(fn):
            self.handlers.append(fn)
            return fn
        return deco

    async def get_me(self):
        return SimpleNamespace(id=999)

    async def __call__(self, request):
        if type(request).__name__ == 'GetFullUserRequest':
            return SimpleNamespace(users=[SimpleNamespace(to_dict=lambda: {})])
        return SimpleNamespace(messages=[])  # downward walk finds nothing older

    async def run_until_disconnected(self):
        for i in (1, 2, 3):
            m = SimpleNamespace(
                id=i, peer_id=PeerUser(user_id=42), from_id=PeerUser(user_id=42), to_id=None,
                date=f'2026-10-10 12:00:0{i}', media=None, message=f'live {i}', action=None,
                reply_to=None, sender=object(), input_chat=None, chat_id=42,
            )

            async def get_chat():
                return SimpleNamespace(id=42)

            await self.handlers[0](SimpleNamespace(message=m, get_chat=get_chat))
        # returning here is the user pressing Ctrl+C


@pytest.mark.asyncio
@pytest.mark.parametrize("accept", [False, True])
async def test_live_messages_reach_disk_and_offer_is_asked_once(monkeypatch, tmp_path, accept):
    bot = FakeBot()

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def start(self, **kw):
            return bot

    offers = []

    async def offer(bot, message_id, lookahead):
        offers.append(message_id)
        if accept:
            await dumper.get_chat_history_down(bot, from_id=message_id + 1, lookahead=lookahead)
        return accept

    async def no_discover(bot, user_id):
        pass

    monkeypatch.setattr(dumper, "TelegramClient", FakeClient)
    monkeypatch.setattr(dumper, "print_bot_info", lambda me: None)
    monkeypatch.setattr(dumper, "chat_display_name", lambda chat: "chat")
    monkeypatch.setattr(dumper, "offer_downward_dump", offer)
    monkeypatch.setattr(dumper, "discover_user", no_discover)

    args = argparse.Namespace(tor=False, token='999:fake', output=str(tmp_path), listen_only=True,
                              start_from_id=0, down=False, lookahead=0)
    await dumper.main(args)

    history = open(os.path.join(tmp_path, '999', '42', '42_history.txt'), encoding='utf-8').read()
    assert [line.split('] ')[-1] for line in history.splitlines()] == ['live 1', 'live 2', 'live 3']
    assert offers == [1]
