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
from telethon.errors.rpcerrorlist import AccessTokenExpiredError, RpcCallFailError
from telethon.tl.types import MessageMediaGeo, MessageMediaPhoto, MessageMediaDocument, MessageMediaContact
from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeAudio, DocumentAttributeVideo, MessageActionChatEditPhoto

API_ID = 0
API_HASH = ''

# messages count per cycle. it's optimal value, seriously
HISTORY_DUMP_STEP = 200
# lookahead counter, useful when supposedly incomplete history
# you can increase it
LOOKAHEAD_STEP_COUNT = 0

# TODO: make not global
all_chats = {}
all_users = {}
messages_by_chat = {}
base_path = ''


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


async def safe_api_request(coroutine, comment):
    result = None
    try:
        result = await coroutine
    except RpcCallFailError as e:
        print(f"Telegram API error, {comment}: {str(e)}")
    except Exception as e:
        print(f"Some error, {comment}: {str(e)}")
    return result


#TODO: save group photos
async def save_user_photos(bot, user):
    user_id = str(user.id)
    user_dir = os.path.join(base_path, user_id)
    result = await safe_api_request(bot(GetUserPhotosRequest(user_id=user.id,offset=0,max_id=0,limit=100)), 'get user photos')
    if not result:
        return
    for photo in result.photos:
        print(f"Saving photo {photo.id}...")
        await safe_api_request(bot.download_file(photo, os.path.join(user_dir, f'{photo.id}.jpg')), 'download user photo')


async def save_media_photo(bot, chat_id, photo):
    user_media_dir = os.path.join(base_path, chat_id, 'media')
    await safe_api_request(bot.download_file(photo, os.path.join(user_media_dir, f'{photo.id}.jpg')), 'download media photo')


def get_document_filename(document):
    for attr in document.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name
        # voice & round video
        if isinstance(attr, DocumentAttributeAudio) or isinstance(attr, DocumentAttributeVideo):
            return f'{document.id}.{document.mime_type.split("/")[1]}'


async def save_media_document(bot, chat_id, document):
    user_media_dir = os.path.join(base_path, chat_id, 'media')
    filename = os.path.join(user_media_dir, get_document_filename(document))
    if os.path.exists(filename):
        old_filename, extension = os.path.splitext(filename)
        filename = f'{old_filename}_{document.id}{extension}'
    await safe_api_request(bot.download_file(document, filename), 'download file')
    return filename


def remove_old_text_history(chat_id):
    user_dir = os.path.join(base_path, str(chat_id))
    history_filename = os.path.join(user_dir, f'{chat_id}_history.txt')
    if os.path.exists(history_filename):
        print(f"Removing old history of {chat_id}...")
        os.remove(history_filename)


def save_text_history(chat_id, messages):
    user_dir = os.path.join(base_path, str(chat_id))
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)
    history_filename = os.path.join(user_dir, f'{chat_id}_history.txt')
    with open(history_filename, 'a', encoding='utf-8') as text_file:
        text_file.write('\n'.join(messages)+'\n')


def save_chats_text_history():
    for m_chat_id, messages_dict in messages_by_chat.items():
        print(f"Saving history of {m_chat_id} as a text...")
        new_messages = messages_dict['buf']
        save_text_history(m_chat_id, new_messages)
        messages_by_chat[m_chat_id]['history'] += new_messages
        messages_by_chat[m_chat_id]['buf'] = []


def get_chat_id(message, bot_id):
    m = message
    m_chat_id = 0
    if isinstance(m.peer_id, PeerUser):
        if not m.to_id or not m.from_id:
            m_chat_id = str(m.peer_id.user_id)
        else:
            if m.from_id and int(m.from_id.user_id) == int(bot_id):
                m_chat_id = str(m.to_id.user_id)
            else:
                m_chat_id = str(m.from_id)
    elif isinstance(m.peer_id, PeerChat):
        m_chat_id = str(m.peer_id.chat_id)

    return m_chat_id


def get_from_id(message, bot_id):
    m = message
    from_id = 0
    if isinstance(m.peer_id, PeerUser):
        if not m.from_id:
            from_id = str(m.peer_id.user_id)
        else:
            from_id = str(m.from_id.user_id)
    elif isinstance(m.peer_id, PeerChat):
        from_id = str(m.from_id.user_id)

    return from_id


async def process_message(bot, m, empty_message_counter=0):
    m_chat_id = get_chat_id(m, bot.id)
    m_from_id = get_from_id(m, bot.id)

    is_from_user = m_chat_id == m_from_id

    if isinstance(m, MessageEmpty):
        empty_message_counter += 1
        return True
    elif empty_message_counter:
        print(f'Empty messages x{empty_message_counter}')
        empty_message_counter = 0

    history_tail = False
    message_text = ''

    if m.media:
        if isinstance(m.media, MessageMediaGeo):
            message_text = f'Geoposition: {m.media.geo.long}, {m.media.geo.lat}'
        elif isinstance(m.media, MessageMediaPhoto):
            await save_media_photo(bot, m_chat_id, m.media.photo)
            message_text = f'Photo: media/{m.media.photo.id}.jpg'
        elif isinstance(m.media, MessageMediaContact):
            message_text = f'Vcard: phone {m.media.phone_number}, {m.media.first_name} {m.media.last_name}, rawdata {m.media.vcard}'
        elif isinstance(m.media, MessageMediaDocument):
            full_filename = await save_media_document(bot, m_chat_id, m.media.document)
            filename = os.path.split(full_filename)[-1]
            message_text = f'Document: media/{filename}'
        else:
            print(m.media)
        #TODO: add other media description
    else:
        if isinstance(m.action, MessageActionChatEditPhoto):
            await save_media_photo(bot, m_chat_id, m.action.photo)
            message_text = f'Photo of chat was changed: media/{m.action.photo.id}.jpg'
        elif m.action:
            message_text = str(m.action)
    if isinstance(m, MessageService):
        #TODO: add text
        pass

    if m.message:
        message_text  = '\n'.join([message_text, m.message]).strip()

    text = f'[{m.id}][{m_from_id}][{m.date}] {message_text}'
    print(text)

    if not m_chat_id in messages_by_chat:
        messages_by_chat[m_chat_id] = {'buf': [], 'history': []}

    messages_by_chat[m_chat_id]['buf'].append(text)

    if is_from_user and m_from_id and m_from_id not in all_users:
        full_user = await bot(GetFullUserRequest(int(m_from_id)))
        user = full_user.users[0]
        print_user_info(user)
        save_user_info(user)
        remove_old_text_history(m_from_id)
        await save_user_photos(bot, user)
        all_users[m_from_id] = user

    return False


async def get_chat_history(bot, from_id=0, to_id=0, chat_id=None, lookahead=0):
    print(f'Dumping history from {from_id} to {to_id}...')
    messages = await bot(GetMessagesRequest(range(to_id, from_id)))
    empty_message_counter = 0
    history_tail = True
    for m in messages.messages:
        is_empty = await process_message(bot, m, empty_message_counter)
        if is_empty:
            empty_message_counter += 1

    if empty_message_counter:
        print(f'Empty messages x{empty_message_counter}')
        history_tail = True

    save_chats_text_history()
    if not history_tail:
        return await get_chat_history(bot, from_id+HISTORY_DUMP_STEP, to_id+HISTORY_DUMP_STEP, chat_id, lookahead)
    else:
        if lookahead:
            return await get_chat_history(bot, from_id+HISTORY_DUMP_STEP, to_id+HISTORY_DUMP_STEP, chat_id, lookahead-1)
        else:
            print('History was fully dumped.')
            return None


async def bot_auth(bot_token, proxy=None):
    # TODO: make not global
    global base_path
    bot_id = bot_token.split(':')[0]
    base_path = bot_id
    if os.path.exists(base_path):
        import time
        new_path = f'{base_path}_{str(int(time.time()))}'
        os.rename(base_path, new_path)
        os.mkdir(base_path)
        shutil.copyfile(f'{new_path}/{base_path}.session', f'{base_path}/{base_path}.session')
    else:
        os.mkdir(base_path)

    # advantages of Telethon using for bots: https://github.com/telegram-mtproto/botapi-comparison
    try:
        bot = await TelegramClient(os.path.join(base_path, bot_id), API_ID, API_HASH, proxy=proxy).start(bot_token=bot_token)
        bot.id = bot_id
    except AccessTokenExpiredError as e:
        print("Token has expired!")
        sys.exit()

    me = await bot.get_me()
    print_bot_info(me)
    user = await bot(GetFullUserRequest(me))
    all_users[me.id] = user
    user_info = user.full_user.to_dict()
    user_info['token'] = bot_token
	
    with open(os.path.join(bot_id, 'bot.json'), 'w') as bot_info_file:
        json.dump(user_info, bot_info_file, default=str)

    return bot


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="Telegram bot token to check")
    parser.add_argument("--listen-only", help="Don't dump all the bot history", action="store_true")
    parser.add_argument("--lookahead", help="Additional cycles to skip empty messages",
                        default=LOOKAHEAD_STEP_COUNT, type=int)
    parser.add_argument("--tor", help="enable Tor socks proxy", action="store_true")
    args = parser.parse_args()

    proxy = (socks.SOCKS5, '127.0.0.1', 9050) if args.tor else None

    loop = asyncio.get_event_loop()

    bot_token = input("Enter token bot: ") if not args.token else args.token

    bot = loop.run_until_complete(bot_auth(bot_token))

    @bot.on(events.NewMessage)
    async def save_new_user_history(event):
        #TODO: old messages processing
        user = event.message.sender
        chat_id = event.message.chat_id
        if not chat_id in all_chats:
            all_chats[chat_id] = event.message.input_chat
            messages_by_chat[chat_id] = {'history': [], 'buf': []}
            #TODO: chat name display
            print('='*20 + f'\nNEW CHAT DETECTED: {chat_id}')
            if user.id not in all_users:
                print_user_info(user)
                save_user_info(user)
                await save_user_photos(bot, user)

        await process_message(bot, event.message)

    if args.listen_only:
        print("Bot history dumping disabled due to `--listen-only` flag, switching to the listen mode...")
    else:
        loop.run_until_complete(get_chat_history(bot, from_id=HISTORY_DUMP_STEP, to_id=0, lookahead=args.lookahead))

    print('Press Ctrl+C to stop listeting for new messages...')
    bot.run_until_disconnected()
