#!/usr/bin/python3
# -*- coding: utf-8 -*-
import sys
import asyncio
import socks
import argparse
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetMessagesRequest

API_ID = 0
API_HASH = ''

parser = argparse.ArgumentParser()
parser.add_argument("--bot-session", help="file with Telegram session")
parser.add_argument("--token", help="Telegram bot token to check")
parser.add_argument("--tor", help="enable Tor socks proxy", action="store_true")
args = parser.parse_args()

proxy = (socks.SOCKS5, '127.0.0.1', 9050) if args.tor else None

bot_token = input("Enter token bot:") if not args.token else args.token
all_chats = {}

def print_bot_info(bot_info):
    print("ID: %s" % bot_info.id)
    print("Name: %s" % bot_info.first_name)
    print("Username: @%(u)s - https://t.me/%(u)s" % {'u': bot_info.username})


def print_user_info(user_info):
    print("ID: %s" % user_info.id)
    print("First name: %s" % user_info.first_name)
    print("Last name: %s" % user_info.last_name)
    if user_info.username:
        print("Username: @%(u)s - https://t.me/%(u)s" % {'u': user_info.username})
    else:
        print("User has no username")

# advantages of Telethon using for bots: https://github.com/telegram-mtproto/botapi-comparison 

session_name = bot_token.split(':')[0]

bot = TelegramClient(session_name, API_ID, API_HASH, proxy=proxy).start(bot_token=bot_token)
loop = asyncio.get_event_loop()

async def get_chat_history(chat):
    messages = await bot.get_messages(chat)
    #TODO: fix telethon.errors.rpcerrorlist.BotMethodInvalidError: The API access for bot users is restricted. The method you tried to invoke cannot be executed as a bot (caused by GetHistoryRequest)
    print(messages)
    return messages


@bot.on(events.NewMessage)
async def echo(event):
    #TODO: old messages processing
    user = event.message.sender
    chat_id = event.message.chat_id
    if not chat_id in all_chats:
        all_chats[chat_id] = {'saved': False}
        print("="*20 + "\nNEW CHAT DETECTED: %s" % chat_id)
        print_user_info(user)
        loop.create_task(get_chat_history(event.message.chat))

me = loop.run_until_complete(bot.get_me())
print_bot_info(me)

bot.run_until_disconnected()
