#!/usr/bin/python3.6
# -*- coding: utf-8 -*-
import os
import sys
import json
import asyncio
import socks
import shutil
import argparse

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetMessagesRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.types import MessageService, MessageEmpty
from telethon.tl.types import PeerUser, PeerChat
from telethon.errors.rpcerrorlist import AccessTokenExpiredError
from telethon.tl.types import MessageMediaGeo, MessageMediaPhoto, MessageMediaDocument, MessageMediaContact
from telethon.tl.types import DocumentAttributeFilename

API_ID = 0
API_HASH = ''

HISTORY_DUMP_STEP = 200

parser = argparse.ArgumentParser()
parser.add_argument("--token", help="Telegram bot token to check")
parser.add_argument("--tor", help="enable Tor socks proxy", action="store_true")
args = parser.parse_args()

proxy = (socks.SOCKS5, '127.0.0.1', 9050) if args.tor else None

all_chats = {}
all_users = {}
messages_by_chat = {}

def print_bot_info(bot_info):
    print(f"ID: {bot_info.id}")
    print(f"Name: {bot_info.first_name}")
    print(f"Username: @{bot_info.username} - https://t.me/{bot_info.username}")


def print_user_info(user_info):
    print("="*20 + f"\nNEW USER DETECTED: {user_info.id}")
    print(f"First name: {user_info.first_name}")
    print(f"Last name: {user_info.last_name}")
    if user_info.username:
        print(f"Username: @{user_info.username} - https://t.me/{user_info.username}")
    else:
        print("User has no username")

def save_user_info(user):
    user_id = str(user.id)
    user_dir = os.path.join(base_path, user_id)
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)
    user_media_dir = os.path.join(base_path, user_id, 'media')
    if not os.path.exists(user_media_dir):
        os.mkdir(user_media_dir)
    json.dump(user.to_dict(), open(os.path.join(user_dir, f'{user_id}.json'), 'w'))

#TODO: save group photos
async def save_user_photos(user):
    user_id = str(user.id)
    user_dir = os.path.join(base_path, user_id)
    result = await bot(GetUserPhotosRequest(user_id=user.id,offset=0,max_id=0,limit=100))
    for photo in result.photos:
        print(f"Saving photo {photo.id}...")
        await bot.download_file(photo, os.path.join(user_dir, f'{photo.id}.jpg'))

async def save_media_photo(chat_id, photo):
    user_media_dir = os.path.join(base_path, str(chat_id), 'media')
    await bot.download_file(photo, os.path.join(user_media_dir, f'{photo.id}.jpg'))

def get_document_filename(doc_attributes):
    for attr in doc_attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name

async def save_media_document(chat_id, document):
    user_media_dir = os.path.join(base_path, str(chat_id), 'media')
    await bot.download_file(document, os.path.join(user_media_dir, get_document_filename(document.attributes)))

def save_text_history(chat_id, messages):
    user_dir = os.path.join(base_path, str(chat_id))
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)
    text_file = open(os.path.join(user_dir, f'{chat_id}_history.txt'), 'w')
    text_file.write('\n'.join(messages))
    text_file.close()

def save_chats_text_history():
    for m_chat_id, text_messages in messages_by_chat.items():
        print(f"Saving history of {m_chat_id} as a text...")
        save_text_history(m_chat_id, text_messages)


bot_token = input("Enter token bot:") if not args.token else args.token
bot_id = bot_token.split(':')[0]

base_path = bot_id
if os.path.exists(base_path):
    print(f"Bot {bot_id} info was dumped earlier, will be rewrited!")
    first_launch = False
else:
    os.mkdir(base_path)
    first_launch = True

# advantages of Telethon using for bots: https://github.com/telegram-mtproto/botapi-comparison 
try:
    bot = TelegramClient(os.path.join(base_path, bot_id), API_ID, API_HASH, proxy=proxy).start(bot_token=bot_token)
except AccessTokenExpiredError as e:
    print("Token has expired!")
    if first_launch:
        shutil.rmtree(base_path)
    sys.exit()

loop = asyncio.get_event_loop()


async def get_chat_history(from_id=200, to_id=0, chat_id=None):
    print(f'Dumping history from {from_id} to {to_id}...')
    messages = await bot(GetMessagesRequest(range(to_id, from_id)))
    history_tail = False
    for m in messages.messages:

        if isinstance(m.to_id, PeerUser):
            m_chat_id = int(m.to_id.user_id) if int(m.from_id) == int(bot_id) else int(m.from_id)

        elif isinstance(m.to_id, PeerChat):
            m_chat_id = m.to_id.chat_id

        if isinstance(m, MessageEmpty):
            history_tail = True
            print('History was fully dumped.')
            break
        if not m.message:
            if m.media:
                if isinstance(m.media, MessageMediaGeo):
                    m.message = f'Geoposition: {m.media.geo.long}, {m.media.geo.lat}'
                elif isinstance(m.media, MessageMediaPhoto):
                    await save_media_photo(m_chat_id, m.media.photo)
                    m.message = f'Photo: media/{m.media.photo.id}.jpg'
                elif isinstance(m.media, MessageMediaContact):
                    m.message = f'Vcard: phone {m.media.phone_number}, {m.media.first_name} {m.media.last_name}, rawdata {m.media.vcard}'
                elif isinstance(m.media, MessageMediaDocument):
                    await save_media_document(m_chat_id, m.media.document)
                    m.message = f'Document: media/{get_document_filename(m.media.document.attributes)}'
                else:
                    print(m.media)
                #TODO: add other media description
            else:
                m.message = m.action
            if isinstance(m, MessageService):
                #TODO: add text
                pass

        text = f'[{m.id}][{m.from_id}][{m.date}] {m.message}'
        print(text)

        if not m_chat_id in messages_by_chat:
            messages_by_chat[m_chat_id] = []

        messages_by_chat[m_chat_id].append(text)

        if m.from_id not in all_users:
            full_user = await bot(GetFullUserRequest(m.from_id))
            user = full_user.user
            print_user_info(user)
            save_user_info(user)
            await save_user_photos(user)
            all_users[m.from_id] = user

    if not history_tail:
        await get_chat_history(from_id+HISTORY_DUMP_STEP, to_id+HISTORY_DUMP_STEP)
        return

    save_chats_text_history()


@bot.on(events.NewMessage)
async def save_new_user_history(event):
    #TODO: old messages processing
    user = event.message.sender
    chat_id = event.message.chat_id
    if not chat_id in all_chats:
        all_chats[chat_id] = event.message.input_chat
        messages_by_chat[chat_id] = []
        #TODO: chat name display
        print('='*20 + f'\nNEW CHAT DETECTED: {chat_id}')
        if user.id not in all_users:
            print_user_info(user)
            save_user_info(user)
            await save_user_photos(user)
    # TODO: new messages saving

if __name__ == '__main__':
    me = loop.run_until_complete(bot.get_me())
    print_bot_info(me)
    user = loop.run_until_complete(bot(GetFullUserRequest(me)))
    all_users[me.id] = user
    json.dump(user.user.to_dict(), open(os.path.join(base_path, 'bot.json'), 'w'))

    loop.run_until_complete(get_chat_history())

    bot.run_until_disconnected()