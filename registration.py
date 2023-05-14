import argparse
import logging
import socket
import tkinter as tk
import asyncio
from enum import Enum

import aiofiles
from anyio import create_task_group

from chat_tools import send_message
from gui import update_tk, TkAppClosed
from socket_manager import create_chat_connection


logger = logging.getLogger(__name__)


class ConnectionStateChanged(Enum):
    INITIATED = 'устанавливается'
    ESTABLISHED = 'установлено'
    CLOSED = 'закрыто'

    def __str__(self):
        return str(self.value)


class RegistrationDone(Exception):
    pass


def get_arguments():
    parser = argparse.ArgumentParser(
        prog='GUI Chat registration',
        description='Client for chat',
    )
    parser.add_argument(
        '-l', '--log',
        dest='logLevel',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level',
        default='INFO',
    )
    parser.add_argument('--hash', type=str, default='user_hash.txt', help='user hash path')
    parser.add_argument('--host', type=str, default='minechat.dvmn.org', help='chat host')
    parser.add_argument('--port', type=int, default=5050, help='write chat port')
    parser.add_argument('--user_name', type=str, default=None, help='user name')
    parser.add_argument('--timeout', type=int, default=10, help='connection error timeout')
    return parser.parse_args()


def create_gui(sending_queue):
    root = tk.Tk()
    root.title('Регистрация в чате')

    main_label = tk.Label(width=20)
    main_label['text'] = 'Введите ваш никнейм'

    nickname_input = tk.Entry(width=40)

    submit_button = tk.Button(width=10)
    submit_button['text'] = 'Ок'

    status_label = tk.Label()
    status_label['text'] = 'Соединение: устанавливается'

    submit_button["command"] = lambda: get_nickname(sending_queue, nickname_input)
    nickname_input.bind("<Return>", lambda event: get_nickname(sending_queue, nickname_input))

    main_label.grid(row=1, column=0, pady=10)
    nickname_input.grid(row=2, column=0, padx=15, pady=5)
    submit_button.grid(row=3, column=0, pady=5)
    status_label.grid(row=4, column=0, pady=10, sticky='w')

    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    return root, status_label, submit_button, nickname_input


def get_nickname(sending_queue, nickname_input):
    user_name = nickname_input.get()
    sending_queue.put_nowait(user_name)
    nickname_input.delete(0, tk.END)


async def update_status_panel(status_label, status_updates_queue):
    while True:
        status = await status_updates_queue.get()
        status_label['text'] = f'Соединение: {status}'


async def register_user(reader, writer, hash_path, user_name):

    if user_name:
        await reader.readline()
        await send_message(writer, '')
        await reader.readline()

        await send_message(writer, user_name)
        message = await reader.readline()
        decoded_message = message.decode()
        logger.info(f'Вы успешно зарегистрированы: {decoded_message}')
        async with aiofiles.open(hash_path, mode='w') as file:
            await file.write(decoded_message)
        tk.messagebox.showinfo('Поздравляем!', 'Вы успешно зарегистрированы')
        raise RegistrationDone()
    else:
        tk.messagebox.showinfo('Ошибка', 'Поле никнейма не может быть пустым')
        await asyncio.sleep(0)


async def handle_connection(args, status_updates_queue, sending_queue):
    chat_host = args.host
    chat_port = args.port
    hash_path = args.hash
    try:
        async with create_chat_connection(chat_host, chat_port) as connection:
            reader, writer = connection
            status_updates_queue.put_nowait(ConnectionStateChanged.ESTABLISHED)

            while True:
                user_name = await sending_queue.get()
                await register_user(reader, writer, hash_path, user_name)

    except (ConnectionError, socket.gaierror):
        status_updates_queue.put_nowait(ConnectionStateChanged.CLOSED)
        logger.info('Connection error')
        await asyncio.sleep(3)


async def main():
    args = get_arguments()

    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=getattr(logging, args.logLevel),
    )

    status_updates_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()

    root, status_label, submit_button, nickname_input = create_gui(sending_queue)

    async with create_task_group() as tg:
        tg.start_soon(update_tk, root)
        tg.start_soon(update_status_panel, status_label, status_updates_queue)
        tg.start_soon(handle_connection, args, status_updates_queue, sending_queue)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, TkAppClosed, RegistrationDone):
        pass
