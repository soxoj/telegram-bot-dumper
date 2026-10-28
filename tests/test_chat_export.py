"""Exercise chat downloads over HTTP using only synthetic local files."""
import importlib.util
import io
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
import zipfile

import pytest


@pytest.fixture
def viewer(monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "webapp" / "server.py"
    spec = importlib.util.spec_from_file_location("chat_export_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DUMP_ROOT", str(tmp_path))
    httpd = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def test_download_contains_only_the_selected_chat(viewer, tmp_path):
    chat = tmp_path / "12345" / "67890"
    (chat / "media").mkdir(parents=True)
    (chat / "photos").mkdir()
    history = "[1][67890][2026-01-01 12:00:00] hello 中文\n"
    (chat / "67890_history.txt").write_text(history, encoding="utf-8")
    (chat / "media" / "sample.bin").write_bytes(b"synthetic media")
    (chat / "avatar.jpg").write_bytes(b"synthetic photo")
    other = chat.parent / "11111"
    other.mkdir()
    (other / "11111_history.txt").write_text("other chat", encoding="utf-8")
    (chat.parent / "bot.json").write_text('{"token": "synthetic"}', encoding="utf-8")

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
    {}, {"bot": "12345"}, {"chat": "67890"},
    {"bot": "../12345", "chat": "67890"},
    {"bot": "12345", "chat": "../11111"},
    {"bot": "12345", "chat": "67890/../11111"},
    {"bot": "12345", "chat": "-1"},
    {"bot": "١٢٣٤٥", "chat": "67890"},
])
def test_invalid_export_parameters_are_rejected(viewer, params):
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?" + urlencode(params))
    assert error.value.code == 400


def test_missing_chat_returns_not_found(viewer):
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?bot=12345&chat=67890")
    assert error.value.code == 404


def test_empty_chat_can_be_exported(viewer, tmp_path):
    (tmp_path / "12345" / "67890").mkdir(parents=True)
    with urlopen(viewer + "/api/export?bot=12345&chat=67890") as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            assert archive.namelist() == ["12345/67890/"]


def test_export_skips_file_and_directory_symlinks(viewer, tmp_path):
    chat = tmp_path / "12345" / "67890"
    chat.mkdir(parents=True)
    (chat / "keep.txt").write_text("selected chat", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside chat", encoding="utf-8")
    other = chat.parent / "11111"
    other.mkdir()
    (other / "other.txt").write_text("other chat", encoding="utf-8")
    (chat / "outside-file.txt").symlink_to(outside / "secret.txt")
    (chat / "outside-directory").symlink_to(outside, target_is_directory=True)
    (chat / "other-chat").symlink_to(other, target_is_directory=True)

    with urlopen(viewer + "/api/export?bot=12345&chat=67890") as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            assert set(archive.namelist()) == {"12345/67890/", "12345/67890/keep.txt"}


@pytest.mark.parametrize("level", ["bot", "chat"])
def test_symlinked_export_root_is_rejected(viewer, tmp_path, level):
    outside = tmp_path / "outside"
    outside.mkdir()
    if level == "bot":
        (outside / "67890").mkdir()
        (tmp_path / "12345").symlink_to(outside, target_is_directory=True)
    else:
        (tmp_path / "12345").mkdir()
        (tmp_path / "12345" / "67890").symlink_to(outside, target_is_directory=True)
    with pytest.raises(HTTPError) as error:
        urlopen(viewer + "/api/export?bot=12345&chat=67890")
    assert error.value.code == 404
