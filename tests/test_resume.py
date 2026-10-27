"""Resume a saved downward walk without a Telegram connection."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import dumper


@pytest.fixture(autouse=True)
def isolated_dump(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in ("all_chats", "all_users", "messages_by_chat"):
        monkeypatch.setattr(dumper, name, {})
    monkeypatch.setattr(dumper, "base_path", str(tmp_path))
    monkeypatch.setattr(dumper, "NO_HISTORY", False)
    monkeypatch.setattr(dumper, "USERS_CSV", False)
    monkeypatch.setattr(dumper, "HISTORY_DUMP_STEP", 3)


def resume_args(tmp_path):
    return SimpleNamespace(
        tor=False, token="999:fake", output=str(tmp_path), resume=True,
        listen_only=False, start_from_id=0, down=False, lookahead=2,
        no_listen=True,
    )


@pytest.mark.asyncio
async def test_resume_preserves_dump_and_skips_probe(monkeypatch, tmp_path):
    directory = tmp_path / "999"
    directory.mkdir()
    (directory / "last_message_id.txt").write_text("450\n", encoding="utf-8")
    (directory / "999.session").write_text("session-data", encoding="utf-8")
    chat_dir = directory / "42"
    chat_dir.mkdir()
    history = chat_dir / "42_history.txt"
    history.write_text("saved history\n", encoding="utf-8")
    user = SimpleNamespace(id=42, to_dict=lambda: {"id": 42})

    class FakeBot:
        def on(self, event):
            return lambda handler: handler

        async def get_me(self):
            return SimpleNamespace(id=999)

        async def __call__(self, request):
            return SimpleNamespace(users=[user])

        async def disconnect(self):
            pass

    bot = FakeBot()
    client = MagicMock()
    client.start = AsyncMock(return_value=bot)
    monkeypatch.setattr(dumper, "TelegramClient", MagicMock(return_value=client))
    monkeypatch.setattr(dumper, "print_bot_info", lambda me: None)
    monkeypatch.setattr(dumper, "print_user_info", lambda me: None)
    monkeypatch.setattr(dumper, "save_user_photos", AsyncMock())
    probe = AsyncMock()
    upward = AsyncMock()
    monkeypatch.setattr(dumper, "probe_max_id", probe)
    monkeypatch.setattr(dumper, "get_chat_history", upward)
    starts = []

    async def walk(bot, from_id, lookahead):
        starts.append((from_id, lookahead))
        await dumper.discover_user(bot, "42")
        dumper.save_text_history("42", ["resumed history"])

    monkeypatch.setattr(dumper, "get_chat_history_down", walk)
    await dumper.main(resume_args(tmp_path))

    assert starts == [(450, 2)]
    probe.assert_not_awaited()
    upward.assert_not_awaited()
    assert history.read_text(encoding="utf-8") == "saved history\nresumed history\n"
    assert (directory / "999.session").read_text(encoding="utf-8") == "session-data"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["999"]


@pytest.mark.asyncio
@pytest.mark.parametrize("contents", [None, "", "not-an-id", "-4", "1.5"])
async def test_bad_checkpoint_fails_before_auth(monkeypatch, tmp_path, contents):
    directory = tmp_path / "999"
    if contents is not None:
        directory.mkdir()
        (directory / "last_message_id.txt").write_text(contents, encoding="utf-8")
    auth = AsyncMock()
    monkeypatch.setattr(dumper, "bot_auth", auth)

    with pytest.raises(SystemExit, match="last_message_id.txt") as error:
        await dumper.main(resume_args(tmp_path))

    assert error.value.code != 0
    auth.assert_not_awaited()


@pytest.mark.asyncio
async def test_interruption_retains_next_unfinished_batch(monkeypatch, tmp_path):
    requests = []

    async def bot(request):
        requests.append(request)
        if len(requests) == 2:
            raise RuntimeError("interrupted request")
        return SimpleNamespace(messages=[SimpleNamespace(id=9)])

    monkeypatch.setattr(dumper, "process_message", AsyncMock(return_value=False))
    flushed = MagicMock()
    monkeypatch.setattr(dumper, "save_chats_text_history", flushed)

    with pytest.raises(RuntimeError, match="interrupted"):
        await dumper.get_chat_history_down(bot, from_id=10)

    assert (tmp_path / "last_message_id.txt").read_text() == "7"
    assert len(requests) == 2
    flushed.assert_called_once()


@pytest.mark.asyncio
async def test_initial_request_failure_keeps_start_id(monkeypatch, tmp_path):
    bot = AsyncMock(side_effect=RuntimeError("request failed"))
    with pytest.raises(RuntimeError, match="request failed"):
        await dumper.get_chat_history_down(bot, from_id=10)
    assert (tmp_path / "last_message_id.txt").read_text() == "10"


@pytest.mark.parametrize("other", [["--listen-only"], ["--start-from-id", "12"]])
def test_resume_rejects_conflicting_start_modes(other):
    with pytest.raises(SystemExit) as error:
        dumper.parse_args(["--resume", *other])
    assert error.value.code == 2


def test_resume_accepts_downward_walk():
    args = dumper.parse_args(["--resume", "--down", "--no-listen"])
    assert args.resume and args.down and args.no_listen
