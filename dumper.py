#!/usr/bin/python3.6
# -*- coding: utf-8 -*-
import os
import sys
import csv
import json
import asyncio
import socks
import shutil
import logging
import argparse

logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s: %(message)s', level=logging.WARNING)

from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetMessagesRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.types import MessageService, MessageEmpty, User
from telethon.tl.types import PeerUser, PeerChat, PeerChannel
from telethon.errors.rpcerrorlist import AccessTokenExpiredError, RpcCallFailError
from telethon.tl.types import MessageMediaGeo, MessageMediaPhoto, MessageMediaDocument, MessageMediaContact
from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeAudio, DocumentAttributeVideo, MessageActionChatEditPhoto

API_ID = 21560964
API_HASH = '6c9a286018e59cae0804765282277231'

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
NO_PHOTOS = False
USERS_CSV = False
NO_MEDIA = False
NO_HISTORY = False

USERS_CSV_FIELDS = [
    'id', 'username', 'first_name', 'last_name',
    'phone', 'lang_code', 'bot', 'premium', 'verified', 'scam', 'fake',
]


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


def chat_display_name(chat):
    title = getattr(chat, 'title', None)
    username = getattr(chat, 'username', None)
    if title:
        return f'"{title}"' + (f' (@{username})' if username else '')
    first = getattr(chat, 'first_name', '') or ''
    last = getattr(chat, 'last_name', '') or ''
    name = (first + ' ' + last).strip()
    if username:
        return f'{name} (@{username})' if name else f'@{username}'
    return name or '?'


def append_user_csv(user):
    path = os.path.join(base_path, 'users.csv')
    is_new = not os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=USERS_CSV_FIELDS, extrasaction='ignore')
        if is_new:
            w.writeheader()
        w.writerow({k: getattr(user, k, '') for k in USERS_CSV_FIELDS})


def save_user_info(user):
    user_id = str(user.id)
    if USERS_CSV:
        append_user_csv(user)
        return
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
    if NO_PHOTOS:
        return
    user_id = str(user.id)
    user_dir = os.path.join(base_path, user_id)
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)
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
    if NO_HISTORY:
        return
    for m_chat_id, messages_dict in messages_by_chat.items():
        new_messages = messages_dict['buf']
        if not new_messages:
            continue
        print(f"Saving history of {m_chat_id} as a text...")
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
    elif isinstance(m.peer_id, PeerChannel):
        m_chat_id = str(m.peer_id.channel_id)

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
    elif isinstance(m.peer_id, PeerChannel):
        if isinstance(m.from_id, PeerUser):
            from_id = str(m.from_id.user_id)
        elif isinstance(m.from_id, PeerChannel):
            from_id = str(m.from_id.channel_id)

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
            if not NO_MEDIA:
                await save_media_photo(bot, m_chat_id, m.media.photo)
            message_text = f'Photo: media/{m.media.photo.id}.jpg'
        elif isinstance(m.media, MessageMediaContact):
            message_text = f'Vcard: phone {m.media.phone_number}, {m.media.first_name} {m.media.last_name}, rawdata {m.media.vcard}'
        elif isinstance(m.media, MessageMediaDocument):
            if NO_MEDIA:
                filename = get_document_filename(m.media.document) or f'{m.media.document.id}'
                message_text = f'Document: media/{filename} (skipped)'
            else:
                full_filename = await save_media_document(bot, m_chat_id, m.media.document)
                filename = os.path.split(full_filename)[-1]
                message_text = f'Document: media/{filename}'
        else:
            print(m.media)
        #TODO: add other media description
    else:
        if isinstance(m.action, MessageActionChatEditPhoto):
            if not NO_MEDIA:
                await save_media_photo(bot, m_chat_id, m.action.photo)
            message_text = f'Photo of chat was changed: media/{m.action.photo.id}.jpg'
        elif m.action:
            message_text = str(m.action)
    if isinstance(m, MessageService):
        #TODO: add text
        pass

    if m.message:
        message_text  = '\n'.join([message_text, m.message]).strip()

    is_group = isinstance(m.peer_id, (PeerChat, PeerChannel))
    is_outgoing_pm = (str(m_from_id) == str(bot.id)
                      and isinstance(m.peer_id, PeerUser)
                      and m_chat_id and str(m_chat_id) != str(m_from_id))
    if is_group:
        text = f'[{m.id}][from:{m_from_id}][group:{m_chat_id}][{m.date}] {message_text}'
    elif is_outgoing_pm:
        text = f'[{m.id}][{m_from_id}][to:{m_chat_id}][{m.date}] {message_text}'
    else:
        text = f'[{m.id}][{m_from_id}][{m.date}] {message_text}'
    print(text)

    if not NO_HISTORY:
        if not m_chat_id in messages_by_chat:
            messages_by_chat[m_chat_id] = {'buf': [], 'history': []}
        messages_by_chat[m_chat_id]['buf'].append(text)

    user_to_resolve = None
    if is_from_user and m_from_id:
        user_to_resolve = m_from_id
    elif (isinstance(m.peer_id, PeerUser)
          and str(m_from_id) == str(bot.id)
          and m_chat_id and str(m_chat_id) != str(bot.id)):
        user_to_resolve = m_chat_id

    if user_to_resolve and user_to_resolve not in all_users:
        await discover_user(bot, user_to_resolve)

    return False


async def discover_user(bot, user_id):
    if not user_id or user_id in all_users:
        return
    full_user = await safe_api_request(bot(GetFullUserRequest(int(user_id))), f'resolve user {user_id}')
    if not full_user or not full_user.users:
        return
    user = full_user.users[0]
    print_user_info(user)
    save_user_info(user)
    remove_old_text_history(user_id)
    await save_user_photos(bot, user)
    all_users[user_id] = user


async def get_chat_history(bot, from_id=0, to_id=0, chat_id=None, lookahead=0):
    print(f'Dumping history from {from_id} to {to_id}...')
    messages = await bot(GetMessagesRequest(range(to_id, from_id)))
    empty_message_counter = 0
    history_tail = True
    for m in messages.messages:
        is_empty = await process_message(bot, m, empty_message_counter)
        if is_empty:
            empty_message_counter += 1
        else:
            empty_message_counter = 0

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


async def probe_max_id(bot, max_pow=9):
    candidates = [10 ** i for i in range(0, max_pow + 1)]
    print(f'Probing max message id with candidates: {candidates}')
    msgs = await bot(GetMessagesRequest(candidates))
    highest = 0
    for m in msgs.messages:
        if not isinstance(m, MessageEmpty):
            print(f'  hit at id={m.id}')
            highest = max(highest, m.id)
    return highest


async def get_chat_history_down(bot, from_id, lookahead=0):
    if from_id <= 1:
        print('Reached the beginning of history.')
        return
    to_id = max(0, from_id - HISTORY_DUMP_STEP)
    print(f'Requesting message ids {from_id - 1}..{to_id} (batch of {from_id - to_id}, walking down)...')
    messages = await bot(GetMessagesRequest(range(to_id, from_id)))
    empty_message_counter = 0
    found_real = False
    for m in messages.messages:
        is_empty = await process_message(bot, m, empty_message_counter)
        if is_empty:
            empty_message_counter += 1
        else:
            empty_message_counter = 0
            found_real = True

    if empty_message_counter:
        print(f'Empty messages x{empty_message_counter}')

    save_chats_text_history()
    if to_id <= 1:
        print('History was fully dumped (down).')
        return
    if found_real:
        return await get_chat_history_down(bot, to_id, lookahead)
    if lookahead:
        return await get_chat_history_down(bot, to_id, lookahead - 1)
    print('No more messages within lookahead window. Stopping.')


def save_last_message_id(message_id):
    path = os.path.join(base_path, 'last_message_id.txt')
    with open(path, 'w') as f:
        f.write(str(message_id))
    return path


async def offer_downward_dump(bot, message_id, lookahead):
    saved_path = save_last_message_id(message_id)
    print(f'\n[!] Live message captured: id={message_id} (saved to {saved_path}).')
    loop = asyncio.get_running_loop()
    answer = await loop.run_in_executor(
        None, input,
        '    Start dumping history DOWN from this id now? [Y/n]: '
    )
    if answer.strip().lower() in ('', 'y', 'yes'):
        await get_chat_history_down(bot, from_id=message_id + 1, lookahead=lookahead)
        print('Downward dump finished. Continuing to listen for new messages...')
        return True
    print(f'Skipped. You can rerun later with: --start-from-id {message_id}')
    return False


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
        old_session = f'{new_path}/{base_path}.session'
        if os.path.exists(old_session):
            shutil.copyfile(old_session, f'{base_path}/{base_path}.session')
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
    user_info = user.users[0].to_dict()
    user_info['token'] = bot_token
	
    with open(os.path.join(bot_id, 'bot.json'), 'w') as bot_info_file:
        json.dump(user_info, bot_info_file, default=str)

    return bot


async def main(args):
    proxy = (socks.SOCKS5, '127.0.0.1', 9050) if args.tor else None
    bot_token = args.token or input("Enter token bot: ")
    bot = await bot_auth(bot_token, proxy=proxy)

    offer_state = {'pending': args.listen_only, 'in_flight': False}

    @bot.on(events.NewMessage)
    async def save_new_user_history(event):
        #TODO: old messages processing
        sender = event.message.sender
        chat = await event.get_chat()
        chat_id = event.message.chat_id
        if not chat_id in all_chats:
            all_chats[chat_id] = event.message.input_chat
            messages_by_chat[chat_id] = {'history': [], 'buf': []}
            print('='*20 + f'\nNEW CHAT DETECTED: {chat_id} {chat_display_name(chat)}')
            if isinstance(sender, User) and sender.id not in all_users:
                print_user_info(sender)
                save_user_info(sender)
                await save_user_photos(bot, sender)

        await process_message(bot, event.message)

        if offer_state['pending'] and not offer_state['in_flight']:
            offer_state['in_flight'] = True
            try:
                accepted = await offer_downward_dump(bot, event.message.id, args.lookahead)
                if accepted:
                    offer_state['pending'] = False
            finally:
                offer_state['in_flight'] = False

    if args.start_from_id:
        await get_chat_history_down(bot, from_id=args.start_from_id, lookahead=args.lookahead)
    elif args.listen_only:
        print("Bot history dumping disabled due to `--listen-only` flag, switching to the listen mode...")
    elif args.down:
        max_id = await probe_max_id(bot)
        if max_id:
            print(f'Highest probed id: {max_id}. Dumping downwards from {max_id + 1}...')
            await get_chat_history_down(bot, from_id=max_id + 1, lookahead=args.lookahead)
        else:
            print('No messages found via id probe. Nothing to dump downwards.')
    else:
        await get_chat_history(bot, from_id=HISTORY_DUMP_STEP, to_id=0, lookahead=args.lookahead)

    print('Press Ctrl+C to stop listeting for new messages...')
    await bot.run_until_disconnected()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="Telegram bot token to check")
    parser.add_argument("--listen-only", help="Don't dump all the bot history", action="store_true")
    parser.add_argument("--lookahead", help="Additional cycles to skip empty messages",
                        default=LOOKAHEAD_STEP_COUNT, type=int)
    parser.add_argument("--batch-size", help="Number of message ids requested per cycle (default: 200)",
                        default=HISTORY_DUMP_STEP, type=int)
    parser.add_argument("--start-from-id", help="Dump history downwards starting from this message id",
                        default=0, type=int)
    parser.add_argument("--down", help="Walk message ids downwards (auto-probes max id if --start-from-id is not set)",
                        action="store_true")
    parser.add_argument("--no-photos", help="Skip downloading user profile photos", action="store_true")
    parser.add_argument("--no-media", help="Skip downloading message media (photos and documents); keep metadata only",
                        action="store_true")
    parser.add_argument("--no-history", help="Do not write per-chat text history files",
                        action="store_true")
    parser.add_argument("--users-csv", help="Save users to a single users.csv instead of per-user JSON dirs",
                        action="store_true")
    parser.add_argument("--tor", help="enable Tor socks proxy", action="store_true")
    args = parser.parse_args()

    NO_PHOTOS = args.no_photos
    USERS_CSV = args.users_csv
    NO_MEDIA = args.no_media
    NO_HISTORY = args.no_history
    HISTORY_DUMP_STEP = max(1, args.batch_size)

    asyncio.run(main(args))
