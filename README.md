# telegram-bot-dumper

Easy dumping of all Telegram bot stuff.

**Input**: only bot token.

**Output**: bot name & info, all chats text history & media, bot's users info & photos.

---

This is a Python implementation.

🚀 Fast [Golang version](https://github.com/soxoj/telegram-bot-dumper-go) by [ScBoln](https://github.com/ScBoln).

## Features

- Dump bot's messages with media content by walking message ids upwards (default) or downwards (`--down` / `--start-from-id`).
- Live listen mode (`--listen-only`): receive new messages in real time and offer to dump history downwards from the first observed id.
- Resolve user info both for incoming messages **and** for outgoing bot replies.
- Lightweight modes for fast user enumeration: skip media, skip per-chat text history, write users to a single CSV.
- Group / supergroup messages are tagged with `[from:USER][group:CHAT]`. Outgoing bot DMs are tagged with `[to:USER]`.
- **Group monitoring**: if the bot has been added to a group/supergroup AND its [privacy mode](https://core.telegram.org/bots/features#privacy-mode) is **disabled**, the bot receives **all** group messages — not just commands and replies — and `--listen-only` will dump them in real time. With privacy mode enabled (the default) the bot only sees commands, mentions, and replies.

## Requirements

- Python >= 3.6
- Telethon (see `requirements.txt` for the pinned version)
- [Register a Telegram application](https://core.telegram.org/api/obtaining_api_id) to get `API_ID` and `API_HASH`

## Using

```sh
pip install -r requirements.txt

vi dumper.py # set API_ID and API_HASH, save
```

### Quick start — full dump (default behavior)

Walks ids 1..∞ upwards in batches of 200, downloading every message, all media, and all user profile photos.

```sh
./dumper.py --token 12345678:ABCe2rPVteUWZ7wLeCqCb3CH3ilUY_fLabc
```

### Dump downwards from the latest message

For an active bot the upward walk hits a long stretch of pruned (deleted/expired) old ids and gives up. Walking down from the most recent id is much more productive. `--down` auto-probes the upper bound (powers of 10 up to 10⁹) and starts from the highest non-empty id it finds:

```sh
./dumper.py --token TOKEN --down
```

> **Note.** Telegram does not retain bot message history forever. Empirically, only the last few hundred thousand messages remain accessible — in our tests a busy bot exposed roughly the last **500K** messages before `messages.getMessages` started returning only `MessageEmpty` for older ids. If your bot has historically processed more traffic than that, the older history is simply gone server-side and no flag will recover it.

If you already know a recent message id (e.g. one you saw in real time), you can skip the probe and start exactly from it:

```sh
./dumper.py --token TOKEN --start-from-id 11922524
```

### Listen mode

Don't dump anything; just watch what arrives. On the first incoming message the script will offer to start a downward dump from that id:

```sh
./dumper.py --token TOKEN --listen-only
```

### Lightweight user enumeration (CSV, no media, no per-chat history)

Useful when you only need a roster of who has talked to the bot — no zips, no jpegs, no per-chat `*_history.txt`.

```sh
./dumper.py --token TOKEN --down --users-csv --no-photos --no-media --no-history
```

Output: `<bot_id>/users.csv` with columns `id, username, first_name, last_name, phone, lang_code, bot, premium, verified, scam, fake`.

### Resume after a crash / FloodWait

The downward walk prints `Requesting message ids X..Y ...` for every batch. If the run is interrupted, restart from the last printed lower bound:

```sh
./dumper.py --token TOKEN --start-from-id <Y>
```

### Tweaking the batch size

Smaller batches → faster feedback in the log and shorter recovery window after a FloodWait. Larger batches → fewer round-trips when scanning sparse / pruned id ranges. Values up to `1000` work fine in practice.

```sh
./dumper.py --token TOKEN --down --batch-size 50
./dumper.py --token TOKEN --down --batch-size 500
./dumper.py --token TOKEN --down --batch-size 1000
```

### Other flags

| Flag | Effect |
| --- | --- |
| `--lookahead N` | After an all-empty batch, keep scanning N more batches before giving up. Useful when ids are sparse. |
| `--no-photos` | Skip downloading user profile photos (avatars). |
| `--no-media` | Skip downloading photos and documents inside messages; metadata is still written to text history. |
| `--no-history` | Don't write per-chat `<chat_id>_history.txt`. Combine with `--users-csv` for the lightest possible run. |
| `--users-csv` | Write users to a single `<bot_id>/users.csv` instead of `<user_id>/<user_id>.json` directories. |
| `--tor` | Route through a local Tor SOCKS5 proxy on `127.0.0.1:9050` (Telegram blocking bypass). |

Run `./dumper.py --help` for the full list.

## Currently known issues

1. **Bot exits before the history is fully dumped.**
   If some messages have been deleted by users, a batch can come back entirely empty and the script may stop too early. Additionally, if the bot has processed a very large amount of traffic, old messages are simply not returned by Telegram's servers anymore — they have been pruned and no flag will recover them. For sparse-but-existing history, bump `--lookahead` to keep scanning past empty stretches:
   ```sh
   # check additionally 5*200 = 1000 ids
   ./dumper.py --token TOKEN --lookahead 5
   ```
   Or just use `--down`, which is much less affected by gaps in old ids.

2. **History was not dumped for group chats (basic groups, supergroups).**
   `messages.getMessages` only returns the bot's PM history; supergroup history requires per-channel calls that bots typically can't make. Group messages are still captured **live** in `--listen-only` mode if group privacy is off (see Features).

## Testing

Offline unit tests (no network, no token):

```sh
pip install -r test-requirements.txt
pytest tests/ --ignore=tests/bot_test.py
```

Integration test against a real bot (requires a working bot token):

```sh
TEST_TOKEN=12345678:... pytest tests/bot_test.py
```

## Token leaks

Dorks examples: [telepot.bot](https://github.com/search?q=telepot.bot&type=Code)
