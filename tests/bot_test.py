import json
import shutil
import os
import pytest
from telethon.sync import TelegramClient

from dumper import *


bot = None


@pytest.mark.asyncio
async def test_dumper():
    global bot

    if os.path.exists('5080069482'):
        shutil.rmtree('5080069482')

    bot = await bot_auth(os.getenv('TEST_TOKEN'))
    assert bot is not None
    base_path = '5080069482'

    await get_chat_history(bot, from_id=200, to_id=0, lookahead=0)

    assert os.path.exists('5080069482') == True

    bot_info = json.load(open('5080069482/bot.json'))
    assert bot_info['bot'] == True

    assert os.path.exists('5080069482/378410969') == True
    assert os.path.exists('5080069482/660191274') == True

    assert os.path.exists('5080069482/378410969/378410969_history.txt') == True
    assert os.path.exists('5080069482/378410969/378410969.json') == True
    assert os.path.exists('5080069482/378410969/1625262736758908858.jpg') == True

    assert os.path.exists('5080069482/660191274/660191274_history.txt') == True

    soxoj_info = json.load(open('5080069482/378410969/378410969.json'))
    soxoj_info['first_name'] == 'Soxoj'

    soxoj_history = open('5080069482/378410969/378410969_history.txt').read()

    assert soxoj_history == """[1][378410969][2021-12-05 13:59:58+00:00] /start
[2][378410969][2021-12-05 14:00:00+00:00] test
[3][378410969][2021-12-05 14:00:20+00:00] Document: media/02.jpeg
[4][378410969][2021-12-05 14:00:40+00:00] Photo: media/5287469397440576034.jpg
[8][378410969][2021-12-05 14:05:57+00:00] 123
[9][5080069482][2021-12-05 14:05:58+00:00] 123
"""

    chat_history = open('5080069482/660191274/660191274_history.txt').read()

    assert chat_history == """[5][378410969][2021-12-05 14:01:23+00:00] MessageActionChatCreate(title='Soxoj & Test Dumper Serjfios34', users=[378410969, 5080069482])
[6][378410969][2021-12-05 14:01:23+00:00] Photo of chat was changed: media/5289906529388049862.jpg
[7][378410969][2021-12-05 14:01:37+00:00] MessageActionChatDeleteUser(user_id=5080069482)
"""


@pytest.fixture(autouse=True)
@pytest.mark.asyncio
async def exit_pytest_first_failure():
    yield
    await bot.disconnect()
    