#!/usr/bin/env python3
"""Telegram-Web-like viewer + live dumper over dumper.py output.

Run:  python webapp/server.py [DUMP_ROOT]
Open: http://127.0.0.1:8010  and paste a bot token.

Hybrid: existing folder data is read on login; after /api/start the real
dumper.py runs in a background thread and streams each processed message
straight to the browser over SSE (no console scraping) while it writes to the
folders as usual. The token's id part (before ':') selects the dump folder.
Read-only viewing is auth-free & local; add sessions if this leaves localhost.
"""
import os
import re
import sys
import json
import queue
import asyncio
import threading
import mimetypes
from urllib.parse import urlparse, parse_qs, unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)  # where dumper.py lives
_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else None
DUMP_ROOT = os.path.abspath(_arg) if _arg else REPO_ROOT
PORT = int(os.environ.get('PORT', '8010'))
HOST = os.environ.get('HOST', '127.0.0.1')  # set HOST=0.0.0.0 to expose (e.g. in Docker)

# [id] [from_id][optional to:/from:/group:] ... [date] text...   (greedy middle backtracks to release the date bracket)
MSG_RE = re.compile(r'^\[(\d+)\]((?:\[[^\]]*\])*)\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[^\]]*)\]\s?(.*)$')
MEDIA_RE = re.compile(r'^(?:Photo|Document|Photo of chat was changed): media/(.+)$')
USER_FIELDS = ('id', 'first_name', 'last_name', 'username', 'bot', 'premium', 'verified', 'scam', 'fake', 'phone')


def _ids(middle):
    return [x[5:] if x.startswith(('from:', 'to:')) else (x[6:] if x.startswith('group:') else x)
            for x in re.findall(r'\[([^\]]*)\]', middle)]


def parse_lines(text, bot_id):
    """Parse history text (one or many messages) into dicts. Continuation lines fold in."""
    msgs = []
    cur = None
    for line in text.split('\n'):
        m = MSG_RE.match(line)
        if m:
            if cur:
                msgs.append(cur)
            ids = _ids(m.group(2))
            frm = ids[0] if ids else ''
            cur = {'id': int(m.group(1)), 'from_id': frm, 'date': m.group(3),
                   'out': frm == str(bot_id), '_lines': [m.group(4)]}
        elif cur is not None:
            cur['_lines'].append(line)
    if cur:
        msgs.append(cur)
    for msg in msgs:
        media, caption = [], []
        for ln in msg.pop('_lines'):
            mm = MEDIA_RE.match(ln.strip())
            (media.append(mm.group(1)) if mm else caption.append(ln))
        msg['media'] = media
        msg['text'] = '\n'.join(caption).strip()
    return msgs


def parse_history(path, bot_id):
    try:
        return parse_lines(open(path, encoding='utf-8').read(), bot_id)
    except OSError:
        return []


def load_user(chat_dir, chat_id):
    p = os.path.join(chat_dir, f'{chat_id}.json')
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {k: d.get(k) for k in USER_FIELDS}


def display_name(user, chat_id):
    name = ' '.join(x for x in (user.get('first_name'), user.get('last_name')) if x).strip()
    return name or (('@' + user['username']) if user.get('username') else f'Chat {chat_id}')


def list_photos(chat_dir):
    """All profile photos (jpg) in a chat/bot dir, sorted -- first is the avatar."""
    if not os.path.isdir(chat_dir):
        return []
    return sorted(f for f in os.listdir(chat_dir)
                  if f.lower().endswith('.jpg') and os.path.isfile(os.path.join(chat_dir, f)))


def find_avatar(chat_dir):
    ph = list_photos(chat_dir)
    return ph[0] if ph else None


def preview(msg):
    if msg is None:
        return ''
    if msg['text']:
        return msg['text'].split('\n')[0]
    if msg['media']:
        return '📎 ' + os.path.basename(msg['media'][0])
    return ''


def list_chats(bot_id):
    root = os.path.join(DUMP_ROOT, bot_id)
    chats = []
    for name in os.listdir(root):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        hist = os.path.join(d, f'{name}_history.txt')
        msgs = parse_history(hist, bot_id) if os.path.exists(hist) else []
        user = load_user(d, name)
        last = msgs[-1] if msgs else None
        chats.append({
            'id': name,
            'name': display_name(user, name),
            'username': user.get('username'),
            'verified': bool(user.get('verified')),
            'scam': bool(user.get('scam') or user.get('fake')),
            'avatar': find_avatar(d),
            'count': len(msgs),
            'last': preview(last),
            'date': last['date'] if last else '',
        })
    chats.sort(key=lambda c: c['date'], reverse=True)
    return chats


def search_messages(bot_id, term, limit=300):
    """Case-insensitive substring search across a bot's whole history, newest first.

    ponytail: scans every history file per query (no index). Fine for one local user;
    add an index only if a bot has enough history to make this feel slow.
    """
    ql = term.lower()
    root = os.path.join(DUMP_ROOT, bot_id)
    out = []
    if not os.path.isdir(root):
        return out
    for name in os.listdir(root):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        hist = os.path.join(d, f'{name}_history.txt')
        if not os.path.isfile(hist):
            continue
        chat_name = display_name(load_user(d, name), name)
        for m in parse_history(hist, bot_id):
            if m['text'] and ql in m['text'].lower():
                out.append({'chat': name, 'chatName': chat_name,
                            'id': m['id'], 'date': m['date'], 'text': m['text']})
    out.sort(key=lambda r: r['date'], reverse=True)
    return out[:limit]


def login(token):
    if ':' not in token or not token.split(':')[0].isdigit():
        return None, 'Invalid token format (expected <id>:<hash>).'
    bot_id = token.split(':')[0]
    root = os.path.join(DUMP_ROOT, bot_id)
    if not os.path.isdir(root):
        return None, f'No dump found for bot {bot_id} in {DUMP_ROOT}.'
    bot = {}
    bp = os.path.join(root, 'bot.json')
    if os.path.exists(bp):
        try:
            bot = json.load(open(bp, encoding='utf-8'))
        except (OSError, ValueError):
            bot = {}
    return {
        'botId': bot_id,
        'bot': {
            'id': bot_id,
            'name': display_name(bot, bot_id),
            'username': bot.get('username'),
            'avatar': find_avatar(root),
        },
        'chats': list_chats(bot_id),
    }, None


def safe_path(bot_id, rel):
    """Resolve DUMP_ROOT/bot_id/rel, refusing anything that escapes the bot folder."""
    base = os.path.realpath(os.path.join(DUMP_ROOT, bot_id))
    full = os.path.realpath(os.path.join(base, rel))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


# ---- live dumping (background thread) + SSE broker -------------------------

class Broker:
    """Fan out events to all connected SSE clients. Thread-safe."""
    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()

    def publish(self, event):
        data = ('data: ' + json.dumps(event, default=str) + '\n\n').encode('utf-8')
        with self.lock:
            for q in list(self.clients):
                q.put(data)

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            self.clients.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients.discard(q)


broker = Broker()
_live = {'bot': None}  # ponytail: one live bot at a time; enough for a single local user


def _on_message(chat_id, line):
    msgs = parse_lines(line, _live['bot'])
    if msgs:
        broker.publish({'type': 'message', 'chat': str(chat_id), 'message': msgs[0]})


def _on_user(user_dict):
    cid = str(user_dict.get('id'))
    d = os.path.join(DUMP_ROOT, _live['bot'], cid)
    broker.publish({'type': 'chat', 'chat': {
        'id': cid,
        'name': display_name(user_dict, cid),
        'username': user_dict.get('username'),
        'verified': bool(user_dict.get('verified')),
        'scam': bool(user_dict.get('scam') or user_dict.get('fake')),
        'avatar': find_avatar(d) if os.path.isdir(d) else None,
    }})


def max_saved_id(bot_id):
    """Highest bot-global message id already on disk (the backfill boundary)."""
    root = os.path.join(DUMP_ROOT, bot_id)
    mx = 0
    if not os.path.isdir(root):
        return 0
    for name in os.listdir(root):
        h = os.path.join(root, name, f'{name}_history.txt')
        if os.path.isfile(h):
            for m in parse_history(h, bot_id):
                mx = max(mx, m['id'])
    return mx


async def _backfill_new(D, client, boundary):
    """Walk ids upward from boundary, streaming each real message, until end of history.

    We don't trust probe_max_id (it only samples powers of ten, so it caps the dump
    at 1000/10000/...). Instead we keep requesting the next batch and stop only after
    `tolerance` consecutive all-empty batches -- enough to jump gaps left by Telegram's
    retention pruning. ponytail: tolerance is a heuristic; raise it if a real gap is wider.
    """
    step = getattr(D, 'HISTORY_DUMP_STEP', 200)
    tolerance = 10  # up to tolerance*step (2000) consecutive empty ids tolerated as a gap
    total, lo, empty, announced = 0, boundary, 0, False
    while True:
        hi = lo + step
        res = await client(D.GetMessagesRequest(list(range(lo + 1, hi + 1))))
        real = sorted((m for m in res.messages if not isinstance(m, D.MessageEmpty)),
                      key=lambda x: x.id)
        if real:
            if not announced:
                broker.publish({'type': 'status', 'status': 'dumping'})
                announced = True
            for m in real:
                await D.process_message(client, m)   # fires ON_MESSAGE -> stream
                total += 1
            D.save_chats_text_history()              # flush to folder
            empty = 0
        else:
            empty += 1
            if empty >= tolerance:
                break
        lo = hi
    return total


async def _live_main(D, token, bot_id):
    from telethon import TelegramClient, events
    client = TelegramClient(os.path.join(D.base_path, bot_id), D.API_ID, D.API_HASH)
    await client.start(bot_token=token)
    client.id = bot_id

    @client.on(events.NewMessage)
    async def _(event):
        try:
            await D.process_message(client, event.message)  # fires ON_MESSAGE -> stream
            D.save_chats_text_history()                      # flush buffer to folder
        except Exception as e:
            broker.publish({'type': 'error', 'error': f'message: {e}'})

    try:
        n = await _backfill_new(D, client, max_saved_id(bot_id))
        broker.publish({'type': 'note', 'text': f'{n} new message(s) dumped'})
    except Exception as e:
        broker.publish({'type': 'error', 'error': f'backfill: {e}'})
    broker.publish({'type': 'status', 'status': 'live'})
    await client.run_until_disconnected()


def _run_live(token, bot_id):
    try:
        sys.path.insert(0, REPO_ROOT)
        import dumper as D
    except Exception as e:
        broker.publish({'type': 'error', 'error': f'cannot import dumper (telethon installed?): {e}'})
        _live['bot'] = None
        return
    # hybrid: append to existing history instead of wiping it, and stream/save live
    D.remove_old_text_history = lambda *a, **k: None
    D.ON_MESSAGE = _on_message
    D.ON_USER = _on_user
    D.base_path = os.path.join(DUMP_ROOT, bot_id)
    os.makedirs(D.base_path, exist_ok=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_live_main(D, token, bot_id))
    except Exception as e:
        broker.publish({'type': 'error', 'error': str(e)})
    finally:
        _live['bot'] = None
        broker.publish({'type': 'status', 'status': 'stopped'})


def start_live(token):
    if ':' not in token or not token.split(':')[0].isdigit():
        return {'error': 'invalid token'}
    bot_id = token.split(':')[0]
    if _live['bot'] == bot_id:
        return {'status': 'already running'}
    if _live['bot']:
        return {'error': f'another bot ({_live["bot"]}) is live; refresh to stop'}
    _live['bot'] = bot_id
    threading.Thread(target=_run_live, args=(token, bot_id), daemon=True).start()
    return {'status': 'starting'}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass  # client (EventSource) dropped the socket; nothing to log

    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/index.html'):
            return self._send_file(os.path.join(HERE, 'index.html'))
        if u.path == '/api/messages':
            q = parse_qs(u.query)
            bot_id, chat = q.get('bot', [''])[0], q.get('chat', [''])[0]
            if not bot_id.isdigit() or not re.fullmatch(r'\d+', chat or ''):
                return self._json({'error': 'bad params'}, 400)
            hist = os.path.join(DUMP_ROOT, bot_id, chat, f'{chat}_history.txt')
            return self._json({'messages': parse_history(hist, bot_id) if os.path.exists(hist) else []})
        if u.path == '/api/search':
            q = parse_qs(u.query)
            bot_id, term = q.get('bot', [''])[0], q.get('q', [''])[0]
            if not bot_id.isdigit():
                return self._json({'error': 'bad params'}, 400)
            if not term.strip():
                return self._json({'results': []})
            return self._json({'results': search_messages(bot_id, term)})
        if u.path == '/api/profile':
            q = parse_qs(u.query)
            bot_id, chat = q.get('bot', [''])[0], q.get('chat', [''])[0]
            if not bot_id.isdigit() or not re.fullmatch(r'\d+', chat or ''):
                return self._json({'error': 'bad params'}, 400)
            d = os.path.join(DUMP_ROOT, bot_id, chat)
            return self._json({'user': load_user(d, chat), 'photos': list_photos(d)})
        if u.path == '/api/stream':
            return self._stream()
        if u.path.startswith('/file/'):
            parts = unquote(u.path[len('/file/'):]).split('/', 1)
            if len(parts) != 2 or not parts[0].isdigit():
                return self._json({'error': 'not found'}, 404)
            full = safe_path(parts[0], parts[1])
            if not full or not os.path.isfile(full):
                return self._json({'error': 'not found'}, 404)
            return self._send_file(full)
        return self._json({'error': 'not found'}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/api/login', '/api/start'):
            return self._json({'error': 'not found'}, 404)
        n = int(self.headers.get('Content-Length', 0))
        try:
            token = json.loads(self.rfile.read(n) or b'{}').get('token', '').strip()
        except ValueError:
            return self._json({'error': 'bad request'}, 400)
        if path == '/api/start':
            return self._json(start_live(token))
        data, err = login(token)
        return self._json(data) if data else self._json({'error': err}, 404)

    def _stream(self):
        q = broker.subscribe()
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            self.wfile.write(b': connected\n\n')
            self.wfile.flush()
            while True:
                try:
                    data = q.get(timeout=15)
                except queue.Empty:
                    data = b': ping\n\n'  # heartbeat keeps the connection open
                self.wfile.write(data)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            broker.unsubscribe(q)

    def _send_file(self, path):
        ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        try:
            data = open(path, 'rb').read()
        except OSError:
            return self._json({'error': 'not found'}, 404)
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def selftest():
    lines = [
        '[69][997476736][2026-08-13 07:15:19+00:00] /start',
        '[129][8443211601][to:997476736][2026-08-13 14:04:32+00:00] hi',
        'second line',
        '[7][8443211601][to:378410969][2026-08-12 13:44:02+00:00] Document: media/report.pdf',
        '@soxoj caption',
        '[9][111][group:222][2026-08-12 13:46:27+00:00] group msg',
    ]
    import tempfile
    p = tempfile.mktemp()
    open(p, 'w').write('\n'.join(lines))
    m = parse_history(p, '8443211601')
    os.remove(p)
    assert len(m) == 4, m
    assert m[0]['from_id'] == '997476736' and not m[0]['out']
    assert m[1]['out'] and m[1]['text'] == 'hi\nsecond line'
    assert m[2]['media'] == ['report.pdf'] and m[2]['text'] == '@soxoj caption'
    assert m[3]['from_id'] == '111' and m[3]['text'] == 'group msg'
    # ON_MESSAGE hook payload is a single (possibly multi-line) message
    live = parse_lines('[7][8443211601][to:1][2026-08-12 13:44:02+00:00] Document: media/a.pdf\ncap', '8443211601')
    assert len(live) == 1 and live[0]['media'] == ['a.pdf'] and live[0]['text'] == 'cap' and live[0]['out']
    assert safe_path('8443211601', '../8443211601/bot.json') is not None
    assert safe_path('8443211601', '../../etc/passwd') is None
    # search across a bot's history (case-insensitive, newest first)
    global DUMP_ROOT
    import tempfile as _tf
    root = _tf.mkdtemp()
    cdir = os.path.join(root, '8443211601', '111')
    os.makedirs(cdir)
    open(os.path.join(cdir, '111_history.txt'), 'w').write(
        '[9][111][2026-08-12 13:46:27+00:00] hello world\n'
        '[10][111][2026-08-13 09:00:00+00:00] BYE world')
    saved, DUMP_ROOT = DUMP_ROOT, root
    res = search_messages('8443211601', 'WORLD')
    DUMP_ROOT = saved
    assert len(res) == 2 and res[0]['id'] == 10, res  # newest first, case-insensitive
    print('selftest ok')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
        sys.exit()
    bots = sorted(n for n in os.listdir(DUMP_ROOT)
                  if n.isdigit() and os.path.exists(os.path.join(DUMP_ROOT, n, 'bot.json')))
    print(f'Dump root: {DUMP_ROOT}')
    print(f'Bots available: {", ".join(bots) or "(none found)"}')
    print(f'Open http://127.0.0.1:{PORT}')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
