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
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
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
        assert call('/api/start', {'token': token})[0] == 401
        # right id, wrong hash, or no dump at all: no login, and the answer says which
        wrong, unknown = call('/api/login', {'token': '12345:guess'}), call('/api/login', {'token': '99999:x'})
        assert wrong[0] == unknown[0] == 401
        assert b'bot.json' in wrong[1] and b'--allow-new-dumps' in unknown[1]
        assert not (tmp_path / '99999').exists()
        for body in ({'token': 123}, {'token': None}, []):
            assert call('/api/login', body)[0] == 400

        status, _, set_cookie = call('/api/login', {'token': token})
        assert status == 200
        sid = set_cookie.split(';')[0]
        assert b'secret chat' in call('/api/messages?bot=12345&chat=67890', cookie=sid)[1]
        # even with a session, the token and the auth key are never served
        assert call('/file/12345/bot.json', cookie=sid)[0] == 404
        assert call('/file/12345/12345.session', cookie=sid)[0] == 404
        # a session for one bot doesn't open another
        assert call('/api/messages?bot=99999&chat=67890', cookie=sid)[0] == 401
    finally:
        httpd.shutdown()


def test_live_events_reach_only_sessions_of_the_live_bot():
    server = _load()
    mine, other = server.broker.subscribe('111'), server.broker.subscribe('222')
    server._live['bot'] = '111'
    server.broker.publish({'type': 'message', 'message': 'hi'})
    assert b'hi' in mine.get_nowait()
    assert other.empty()


class FakeClient:
    """Stands in for telethon.TelegramClient: accepts only GOOD, writes a session like the real one."""
    GOOD = '777:good'

    def __init__(self, session, api_id, api_hash):
        self.session = session

    async def start(self, bot_token):
        open(self.session + '.session', 'w').close()
        if bot_token != self.GOOD:
            raise ValueError('The api_id/api_hash combination is invalid')
        return self

    async def get_me(self):
        from types import SimpleNamespace
        return SimpleNamespace(to_dict=lambda: {'id': 777, 'first_name': 'Newbie', 'username': 'new_bot'})

    async def disconnect(self):
        pass


def test_allow_new_dumps_creates_bot_json_only_for_a_token_telegram_accepts(tmp_path, monkeypatch):
    import json
    import sys
    import telethon
    server = _load()
    sys.path.insert(0, server.REPO_ROOT)
    import dumper
    monkeypatch.setattr(telethon, 'TelegramClient', FakeClient)
    monkeypatch.setattr(dumper, 'API_ID', 1)
    monkeypatch.setattr(dumper, 'API_HASH', 'h')
    monkeypatch.setattr(server, 'DUMP_ROOT', str(tmp_path))
    monkeypatch.setattr(server, 'ALLOW_NEW_DUMPS', True)

    data, err = server.login('777:bad')
    assert data is None and 'rejected' in err
    assert not (tmp_path / '777').exists()  # no half-made folder left behind

    data, err = server.login(FakeClient.GOOD)
    assert err is None and data['bot']['name'] == 'Newbie' and data['chats'] == []
    saved = json.loads((tmp_path / '777' / 'bot.json').read_text())
    assert saved['token'] == FakeClient.GOOD and saved['username'] == 'new_bot'

    # the folder exists now, so the next login is the usual bot.json check
    assert server.login('777:bad')[0] is None and 'bot.json' in server.login('777:bad')[1]
    assert server.login(FakeClient.GOOD)[0]['botId'] == '777'


def test_allow_new_dumps_needs_api_credentials(tmp_path, monkeypatch):
    import sys
    server = _load()
    sys.path.insert(0, server.REPO_ROOT)
    import dumper
    monkeypatch.setattr(dumper, 'API_ID', 0)
    monkeypatch.setattr(server, 'DUMP_ROOT', str(tmp_path))
    monkeypatch.setattr(server, 'ALLOW_NEW_DUMPS', True)
    data, err = server.login('777:x')
    assert data is None and 'API_ID' in err and not (tmp_path / '777').exists()


def test_allow_new_dumps_refuses_a_public_host_without_allow_public(tmp_path):
    import subprocess
    import sys
    env = {**os.environ, 'HOST': '0.0.0.0', 'PORT': '0', 'ALLOW_NEW_DUMPS': '1'}
    env.pop('ALLOW_PUBLIC', None)
    r = subprocess.run([sys.executable, SERVER, str(tmp_path)], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode != 0 and '--allow-public' in r.stderr
