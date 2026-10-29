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


def test_viewer_has_download_all_button():
    html = Path(__file__).parents[1].joinpath('webapp', 'index.html').read_text(encoding='utf-8')

    assert 'id="export-all"' in html
    assert 'Download all' in html
    assert '/api/export?bot=' in html


def test_viewer_shows_one_pane_at_phone_width():
    html = Path(__file__).parents[1].joinpath('webapp', 'index.html').read_text(encoding='utf-8')

    assert '@media (max-width:700px)' in html
    assert 'id="back"' in html
    assert "$('#app').classList.add('chat')" in html
    assert "$('#app').classList.remove('chat')" in html


def test_viewer_requires_the_real_token_and_hides_secrets(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request

    server = _load()
    token = '12345:real-secret'
    (tmp_path / '12345' / '67890').mkdir(parents=True)
    (tmp_path / '12345' / 'bot.json').write_text(json.dumps({'token': token}), encoding='utf-8')
    (tmp_path / '12345' / '12345.session').write_bytes(b'auth key')
    (tmp_path / '12345' / '67890' / '67890_history.txt').write_text(
        '[1][67890][2026-01-01 12:00:00] secret chat\n', encoding='utf-8')
    server.DUMP_ROOT = str(tmp_path)
    httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_port}'

    def call(path, body=None, cookie=None):
        req = urllib.request.Request(base + path, data=body and json.dumps(body).encode(),
                                     headers={'Cookie': cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers.get('Set-Cookie')
        except urllib.error.HTTPError as e:
            return e.code, e.read(), None

    try:
        # no session: nothing is readable, whatever the bot id
        assert call('/api/messages?bot=12345&chat=67890')[0] == 401
        assert call('/file/12345/bot.json')[0] == 401
        assert call('/api/export?bot=12345&chat=67890')[0] == 401
        assert call('/api/export?bot=12345')[0] == 401
        assert call('/api/start', {'token': token})[0] == 401
        # right id, wrong hash: no login
        assert call('/api/login', {'token': '12345:guess'})[0] == 404

        status, _, set_cookie = call('/api/login', {'token': token})
        assert status == 200
        sid = set_cookie.split(';')[0]
        assert b'secret chat' in call('/api/messages?bot=12345&chat=67890', cookie=sid)[1]
        assert call('/api/export?bot=12345', cookie=sid)[0] == 200
        # even with a session, the token and the auth key are never served
        assert call('/file/12345/bot.json', cookie=sid)[0] == 404
        assert call('/file/12345/12345.session', cookie=sid)[0] == 404
        # a session for one bot doesn't open another
        assert call('/api/messages?bot=99999&chat=67890', cookie=sid)[0] == 401
    finally:
        httpd.shutdown()
