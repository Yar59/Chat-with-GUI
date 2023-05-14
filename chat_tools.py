import asyncio
import json
import logging
from asyncio import sleep
from datetime import datetime
from tkinter import messagebox

import aiofiles

from gui import ReadConnectionStateChanged, SendingConnectionStateChanged, NicknameReceived
from socket_manager import create_chat_connection

logger = logging.getLogger(__name__)


class InvalidToken(Exception):
    pass


def load_chat_history(history_path, messages_queue):
    try:
        with open(history_path, 'r') as file:
            old_messages = file.read()
        messages_queue.put_nowait(old_messages)
        logger.debug('Chat history loaded')
    except FileNotFoundError:
        logger.debug('Chat history not found')


async def handle_chat_reply(reader, watchdog_queue, purpose):
    raw_message = await reader.readline()
    decoded_message = raw_message.decode()
    watchdog_queue.put_nowait(f'Message sent. {purpose}')
    return decoded_message


async def send_message(writer, message):
    sanitized_message = message.replace(r"\n", " ")
    logger.debug(f'Sending message: {sanitized_message}')
    writer.write(f'{sanitized_message}\n'.encode())
    await writer.drain()


async def get_token(hash_path):
    try:
        async with aiofiles.open(hash_path, mode='r') as f:
            contents = await f.read()
            user_payload = json.loads(contents)
        return user_payload['account_hash']
    except FileNotFoundError:
        return


async def authorize_user(reader, writer, user_token):
    await send_message(writer, user_token)

    submit_hash_message = await reader.readline()
    logger.debug(submit_hash_message.decode())

    submit_hash_message_payload = json.loads(submit_hash_message)
    return submit_hash_message_payload


async def handle_message_sending(
    chat_host,
    chat_port,
    user_token,
    messages_queue,
    sending_queue,
    status_updates_queue,
    watchdog_queue,
):
    status_updates_queue.put_nowait(SendingConnectionStateChanged.INITIATED)
    async with create_chat_connection(chat_host, chat_port) as connection:
        reader, writer = connection
        status_updates_queue.put_nowait(SendingConnectionStateChanged.ESTABLISHED)

        connection_message = await reader.readline()
        logger.debug(connection_message.decode())

        if user_token is None:
            login_message = 'Токен не обнаружен, пройдите регистрацию'
            logger.info(login_message)
            messagebox.showinfo('InvalidToken', login_message)
            raise InvalidToken

        submit_hash_message_payload = await authorize_user(reader, writer, user_token)
        if submit_hash_message_payload is None:
            login_message = 'Токен недействителен, пройдите регистрацию заново или проверьте его и перезапустите программу'
            logger.info(login_message)
            messagebox.showinfo('InvalidToken', login_message)
            raise InvalidToken

        username = NicknameReceived(submit_hash_message_payload["nickname"])
        status_updates_queue.put_nowait(username)
        login_message = f'Вы авторизованы как {username.nickname}\n'
        messages_queue.put_nowait(login_message)
        watchdog_queue.put_nowait('Authorization done')
        logger.info(login_message)

        while True:
            message = await sending_queue.get()
            if message != '':
                messages_queue.put_nowait(f'[{datetime.now().strftime("%d.%m.%y %H:%M")}] Вы: {message}\n')
                await handle_chat_reply(reader, watchdog_queue, 'User message')
            await send_message(writer, message)
            await handle_chat_reply(reader, watchdog_queue, 'Ping-pong')
            await sleep(0)


async def read_messages(
    chat_host,
    chat_port,
    messages_queue,
    save_messages_queue,
    status_updates_queue,
    watchdog_queue,
):
    status_updates_queue.put_nowait(ReadConnectionStateChanged.INITIATED)
    async with create_chat_connection(chat_host, chat_port) as connection:
        reader, writer = connection
        status_updates_queue.put_nowait(ReadConnectionStateChanged.ESTABLISHED)
        while not reader.at_eof():
            try:
                message = await reader.readline()
                decoded_message = f'[{datetime.now().strftime("%d.%m.%y %H:%M")}] {message.decode()}'
                messages_queue.put_nowait(decoded_message)
                save_messages_queue.put_nowait(decoded_message)
                watchdog_queue.put_nowait('New message in chat')
                await sleep(0)
            except asyncio.CancelledError:
                logger.debug('Closing connection')
                writer.close()
                raise


async def save_messages(history_path, queue):
    while True:
        message = await queue.get()
        async with aiofiles.open(history_path, mode='a') as file:
            await file.write(message)
