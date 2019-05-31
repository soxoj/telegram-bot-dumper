# telegram-bot-dumper

Easy dumping of all Telegram bot stuff.

**Input**: only bot token.

**Output**: bot name & info, active dialog history, bot's users info, photos & history.

Experimental support of message bruteforcing by id. 

## Requirements

- Python 3.6
- Telethon >= 1.8.0

## Using

```sh
pip install -r requirements.txt

./dumper.py --brute --token 12345678:ABCe2rPVteUWZ7wLeCqCb3CH3ilUY_fLabc
```
