#!/usr/bin/python3.6
# -*- coding: utf-8 -*-
import os
import sys
import json
import asyncio
import socks
import argparse
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetMessagesRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest

API_ID = 0
API_HASH = ''

parser = argparse.ArgumentParser()
parser.add_argument("--bot-session", help="file with Telegram session")
parser.add_argument("--token", help="Telegram bot token to check")
parser.add_argument("--tor", help="enable Tor socks proxy", action="store_true")
parser.add_argument("--brute", help="enable active messages downloading", action="store_true")
args = parser.parse_args()

proxy = (socks.SOCKS5, '127.0.0.1', 9050) if args.tor else None

bot_token = input("Enter token bot:") if not args.token else args.token
all_chats = {}
all_users = {}

def print_bot_info(bot_info):
    print("ID: %s" % bot_info.id)
    print("Name: %s" % bot_info.first_name)
    print("Username: @%(u)s - https://t.me/%(u)s" % {'u': bot_info.username})


def print_user_info(user_info):
    print("="*20 + "\nNEW USER DETECTED: %s" % user_info.id)
    print("First name: %s" % user_info.first_name)
    print("Last name: %s" % user_info.last_name)
    if user_info.username:
        print("Username: @%(u)s - https://t.me/%(u)s" % {'u': user_info.username})
    else:
        print("User has no username")

def save_user_info(user):
    user_id = str(user.id)
    user_dir = os.path.join(base_path, user_id)
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)
    json.dump(user.to_dict(), open(os.path.join(user_dir, '%s.json' % user_id), 'w'))

#TODO: save group photos
async def save_user_photos(user):
    user_id = str(user.id)
    user_dir = os.path.join(base_path, user_id)
    result = await bot(GetUserPhotosRequest(user_id=user.id,offset=0,max_id=0,limit=100))
    for photo in result.photos:
        print("Saving photo %s..." % photo.id)
        await bot.download_file(photo, os.path.join(user_dir, '%s.jpg' % photo.id))


def save_text_history(chat_id, messages):
    user_dir = os.path.join(base_path, str(chat_id))
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)
    text_file = open(os.path.join(user_dir, '%s_history.txt' % chat_id), 'w')
    text_file.write('\n'.join(messages))
    text_file.close()


bot_id = bot_token.split(':')[0]
base_path = bot_id
if os.path.exists(base_path):
    print("Bot %s info was dumped earlier, will be rewrited!" % bot_id)
else:
    os.mkdir(base_path)

# advantages of Telethon using for bots: https://github.com/telegram-mtproto/botapi-comparison 
bot = TelegramClient(os.path.join(base_path, bot_id), API_ID, API_HASH, proxy=proxy).start(bot_token=bot_token)
loop = asyncio.get_event_loop()

async def get_chat_history(from_id, to_id=0, chat_id=None):
    messages = await bot(GetMessagesRequest(range(to_id, from_id)))
    text_messages = []
    for m in messages.messages:
        if not m.from_id:
            continue
        text = "[%s][%s] %s" % (m.from_id, m.date, m.message)
        print(text)
        text_messages.append(text)
        if m.from_id not in all_users:
            full_user = await bot(GetFullUserRequest(m.from_id))
            user = full_user.user
            print_user_info(user)
            save_user_info(user)
            await save_user_photos(user)
            all_users[m.from_id] = user

    print("Saving history of %s as a text..." % chat_id)
    save_text_history(chat_id, text_messages)
    return text_messages

@bot.on(events.NewMessage)
async def save_new_user_history(event):
    #TODO: old messages processing
    user = event.message.sender
    chat_id = event.message.chat_id
    if not chat_id in all_chats:
        all_chats[chat_id] = event.message.input_chat
        #TODO: chat name display
        print("="*20 + "\nNEW CHAT DETECTED: %s" % chat_id)
        if user.id not in all_users:
            print_user_info(user)
            save_user_info(user)
            await save_user_photos(user)
        loop.create_task(get_chat_history(event.message.id, chat_id=chat_id))


if __name__ == '__main__':
    me = loop.run_until_complete(bot.get_me())
    print_bot_info(me)
    user = loop.run_until_complete(bot(GetFullUserRequest(me)))
    all_users[me.id] = user
    json.dump(user.user.to_dict(), open(os.path.join(base_path, 'bot.json'), 'w'))

    if args.brute:
        #TODO: active chat detecting
        #TODO: get messages from other chats
        loop.create_task(get_chat_history(1000, chat_id='active_chat'))

    bot.run_until_disconnected()