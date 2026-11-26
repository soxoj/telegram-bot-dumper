"""Exercise whole-dump and chat downloads over HTTP using only synthetic local files."""
import importlib.util
import io
import os
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen as _urlopen
import zipfile

import pytest


def urlopen(url):
    """Every request comes from a viewer logged in to bot 12345."""
    return _urlopen(Request(url, headers={"Cookie": "sid=test"}))


@pytest.fixture
def viewer(monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "webapp" / "server.py"
    spec = importlib.util.spec_from_file_location("chat_export_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DUMP_ROOT", str(tmp_path))
    monkeypatch.setitem(module.SESSIONS, "test", "12345")
    httpd = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def test_download_entire_bot_dump(viewer, tmp_path):
    bot_dir = tmp_path / "12345"
    chat1 = bot_dir / "67890"
    chat2 = bot_dir / "11111"
    (chat1 / "media").mkdir(parents=True)
    (chat1 / "photos").mkdir()
    chat2.mkdir(parents=True)
    history1 = "[1][67890][2026-01-01 12:00:00] hello 中文\n"
    history2 = "[2][11111][2026-01-01 12:05:00] other chat\n"
    (chat1 / "67890_history.txt").write_text(history1, encoding="utf-8", newline="\n")
    (chat1 / "media" / "sample.bin").write_bytes(b"synthetic media")
    (chat1 / "avatar.jpg").write_bytes(b"chat photo")
    (chat2 / "11111_history.txt").write_text(history2, encoding="utf-8", newline="\n")
    (bot_dir / "bot.json").write_text('{"token": "synthetic"}', encoding="utf-8", newline="\n")
    (bot_dir / "avatar.jpg").write_bytes(b"bot avatar")

    with urlopen(viewer + "/api/export?bot=12345") as response:
        body = response.read()
        assert response.headers["Content-Type"] == "application/zip"
        assert response.headers["Content-Disposition"] == 'attachment; filename="dump_12345.zip"'
        assert int(response.headers["Content-Length"]) == len(body)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert set(archive.namelist()) == {
            "12345/", "12345/bot.json", "12345/avatar.jpg",
            "12345/67890/", "12345/67890/media/", "12345/67890/photos/",
            "12345/67890/67890_history.txt", "12345/67890/media/sample.bin",
            "12345/67890/avatar.jpg",
            "12345/11111/", "12345/11111/11111_history.txt",
        }
        assert archive.read("12345/bot.json").decode("utf-8") == '{"token": "synthetic"}'
        assert archive.read("12345/67890/67890_history.txt").decode("utf-8") == history1
        assert archive.read("12345/67890/media/sample.bin") == b"synthetic media"
        assert archive.read("12345/11111/11111_history.txt").decode("utf-8") == history2
        assert archive.read("12345/avatar.jpg") == b"bot avatar"


def test_download_contains_only_the_selected_chat(viewer, tmp_path):
    chat = tmp_path / "12345" / "67890"
    (chat / "media").mkdir(parents=True)
    (chat / "photos").mkdir()
    history = "[1][67890][2026-01-01 12:00:00] hello 中文\n"
    (chat / "67890_history.txt").write_text(history, encoding="utf-8", newline="\n")
    (chat / "media" / "sample.bin").write_bytes(b"synthetic media")
    (chat / "avatar.jpg").write_bytes(b"synthetic photo")
    other = chat.parent / "11111"
    other.mkdir()
    (other / "11111_history.txt").write_text("other chat\n", encoding="utf-8", newline="\n")
    (chat.parent / "bot.json").write_text('{"token": "synthetic"}', encoding="utf-8", newline="\n")

    with urlopen(viewer + "/api/export?bot=12345&chat=67890") as response:
        body = response.read()
        assert response.headers["Content-Type"] == "application/zip"
        assert response.headers["Content-Disposition"] == 'attachment; filename="dump_12345_67890.zip"'
        assert int(response.headers["Content-Length"]) == len(body)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert set(archive.namelist()) == {
            "12345/67890/", "12345/67890/media/", "12345/67890/photos/",
            "12345/67890/67890_history.txt", "12345/67890/media/sample.bin",
            "12345/67890/avatar.jpg",
        }
        assert archive.read("12345/67890/67890_history.txt").decode("utf-8") == history
        assert archive.read("12345/67890/media/sample.bin") == b"synthetic media"


@pytest.mark.parametrize("params", [
    {}, {"chat": "67890"}, {"bot": ""},
    {"bot": "12345", "chat": ""},
    {"bot": "../12345"},
    {"bot": "../12345", "chat": "67890"},
    {"bot": "12345", "chat": "../11111"},
    {"bot": "12345", "chat": "67890/../11111"},
    {"bot": "-1"},
    {"bot": "12345", "chat": "-1"},
    {"bot": "١٢٣٤٥"},
    {"bot": "١٢٣٤٥", "chat": "67890"},
])
def test_invalid_export_parameters_are_rejected(viewer, params):
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?" + urlencode(params))
    assert error.value.code in (400, 401)  # a different bot id is turned away at login


def test_missing_chat_returns_not_found(viewer):
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?bot=12345&chat=67890")
    assert error.value.code == 404


def test_missing_bot_dump_returns_not_found(viewer):
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?bot=12345")
    assert error.value.code == 404


def test_empty_chat_can_be_exported(viewer, tmp_path):
    (tmp_path / "12345" / "67890").mkdir(parents=True)
    with urlopen(viewer + "/api/export?bot=12345&chat=67890") as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            assert archive.namelist() == ["12345/67890/"]


def test_empty_bot_dump_can_be_exported(viewer, tmp_path):
    (tmp_path / "12345").mkdir(parents=True)
    with urlopen(viewer + "/api/export?bot=12345") as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            assert archive.namelist() == ["12345/"]


def test_export_skips_file_and_directory_symlinks(viewer, tmp_path):
    chat = tmp_path / "12345" / "67890"
    chat.mkdir(parents=True)
    (chat / "keep.txt").write_text("selected chat\n", encoding="utf-8", newline="\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside chat\n", encoding="utf-8", newline="\n")
    other = chat.parent / "11111"
    other.mkdir()
    (other / "other.txt").write_text("other chat\n", encoding="utf-8", newline="\n")
    try:
        (chat / "outside-file.txt").symlink_to(outside / "secret.txt")
        (chat / "outside-directory").symlink_to(outside, target_is_directory=True)
        (chat / "other-chat").symlink_to(other, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported or permitted on this platform")

    with urlopen(viewer + "/api/export?bot=12345&chat=67890") as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            assert set(archive.namelist()) == {"12345/67890/", "12345/67890/keep.txt"}


def test_export_whole_dump_skips_symlinks(viewer, tmp_path):
    bot = tmp_path / "12345"
    bot.mkdir(parents=True)
    (bot / "keep.txt").write_text("bot file\n", encoding="utf-8", newline="\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside chat\n", encoding="utf-8", newline="\n")
    try:
        (bot / "outside-file.txt").symlink_to(outside / "secret.txt")
        (bot / "outside-directory").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported or permitted on this platform")

    with urlopen(viewer + "/api/export?bot=12345") as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            assert set(archive.namelist()) == {"12345/", "12345/keep.txt"}


@pytest.mark.parametrize("level", ["bot", "chat"])
def test_symlinked_export_root_is_rejected(viewer, tmp_path, level):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        if level == "bot":
            (outside / "67890").mkdir()
            (tmp_path / "12345").symlink_to(outside, target_is_directory=True)
        else:
            (tmp_path / "12345").mkdir()
            (tmp_path / "12345" / "67890").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported or permitted on this platform")
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?bot=12345&chat=67890")
    assert error.value.code == 404


def test_symlinked_bot_dump_root_is_rejected(viewer, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / "12345").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported or permitted on this platform")
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?bot=12345")
    assert error.value.code == 404
