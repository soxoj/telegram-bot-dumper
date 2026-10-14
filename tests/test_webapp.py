"""Run the webapp server's built-in self-check under pytest.

server.py already asserts its parsing/search/path-safety invariants in selftest();
this just wires that into `pytest tests/`. telethon/dumper are imported lazily
inside server.py, so importing it here needs no token and no network.
"""
import importlib.util
import os
from pathlib import Path

SERVER = os.path.join(os.path.dirname(__file__), '..', 'webapp', 'server.py')


def _load():
    spec = importlib.util.spec_from_file_location('webapp_server', SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_webapp_selftest():
    _load().selftest()  # asserts inside; raises on any failure


def test_export_links_csv_collects_links_with_sender_ids(tmp_path):
    server = _load()
    bot_id = '12345'
    chat_dir = tmp_path / bot_id / '67890'
    chat_dir.mkdir(parents=True)
    (chat_dir / '67890_history.txt').write_text(
        '[1][67890][2026-01-01 12:00:00] hello https://example.com\n'
        '[2][12345][to:67890][2026-01-01 12:01:00] see http://example.org/a?b=1\n',
        encoding='utf-8',
    )

    saved, server.DUMP_ROOT = server.DUMP_ROOT, str(tmp_path)
    try:
        csv_text = server.links_csv(bot_id)
    finally:
        server.DUMP_ROOT = saved

    assert csv_text.splitlines() == [
        'link,sender_id',
        'https://example.com,67890',
        'http://example.org/a?b=1,12345',
    ]


def test_viewer_has_export_links_button():
    html = Path(__file__).parents[1].joinpath('webapp', 'index.html').read_text(encoding='utf-8')

    assert 'id="export-links"' in html
    assert '/api/links.csv?bot=' in html


def test_viewer_shows_one_pane_at_phone_width():
    html = Path(__file__).parents[1].joinpath('webapp', 'index.html').read_text(encoding='utf-8')

    assert '@media (max-width:700px)' in html
    assert 'id="back"' in html
    assert "$('#app').classList.add('chat')" in html
    assert "$('#app').classList.remove('chat')" in html
