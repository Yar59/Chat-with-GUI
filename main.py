import asyncio
import logging
import socket
from datetime import datetime

from async_timeout import timeout
from anyio import create_task_group, ExceptionGroup

import gui
from chat_tools import (
    read_messages,
    get_arguments,
    get_token,
    save_messages,
    load_chat_history,
    handle_message_sending,
    InvalidToken,
)

logger = logging.getLogger(__name__)
watchdog_logger = logging.getLogger('watchdog')


async def ping_pong(sending_queue, ping_delay):
    while True:
        sending_queue.put_nowait('')
        await asyncio.sleep(ping_delay)


async def handle_connection(
    chat_host,
    chat_port_listen,
    history_path,
    sending_queue,
    chat_port_write,
    user_token,
    connection_timeout,
    ping_delay,
    messages_queue,
    save_messages_queue,
    status_updates_queue,
    watchdog_queue,
):
    while True:
        try:
            async with create_task_group() as tg:
                tg.start_soon(
                    read_messages,
                    chat_host,
                    chat_port_listen,
                    messages_queue,
                    save_messages_queue,
                    status_updates_queue,
                    watchdog_queue,
                )
                tg.start_soon(
                    save_messages,
                    history_path,
                    save_messages_queue,
                )
                tg.start_soon(
                    handle_message_sending,
                    chat_host,
                    chat_port_write,
                    user_token,
                    messages_queue,
                    sending_queue,
                    status_updates_queue,
                    watchdog_queue,
                )
                tg.start_soon(
                    watch_for_connection,
                    watchdog_queue,
                    connection_timeout,
                )
                tg.start_soon(
                    ping_pong,
                    sending_queue,
                    ping_delay,
                )
        except (ExceptionGroup, ConnectionError, socket.gaierror):
            status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.CLOSED)
            status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.CLOSED)
            logger.info('Connection error')
            await asyncio.sleep(3)


async def watch_for_connection(watchdog_queue, connection_timeout):
    while True:
        try:
            async with timeout(connection_timeout) as cm:
                message = await watchdog_queue.get()
                message = f'[{datetime.now().timestamp()}] Connection is alive. {message}'
                watchdog_logger.info(message)
        except asyncio.exceptions.TimeoutError:
            if cm.expired:
                watchdog_logger.info(f'[{datetime.now().timestamp()}] {connection_timeout}s timeout is elapsed')
                raise ConnectionError()


async def main():
    args = get_arguments()
    chat_host = args.host
    chat_port_write = args.port_write
    chat_port_listen = args.port_listen
    hash_path = args.hash
    user_token = args.token or await get_token(hash_path)
    user_name = args.user_name
    log_level = args.logLevel
    history_path = args.history
    connection_timeout = args.timeout
    ping_delay = args.ping

    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=getattr(logging, log_level),
    )

    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    save_messages_queue = asyncio.Queue()
    watchdog_queue = asyncio.Queue()

    load_chat_history(history_path, messages_queue)

    async with create_task_group() as tg:
        tg.start_soon(
            gui.draw,
            messages_queue,
            sending_queue,
            status_updates_queue,
        )
        tg.start_soon(
            handle_connection,
            chat_host,
            chat_port_listen,
            history_path,
            sending_queue,
            chat_port_write,
            user_token,
            connection_timeout,
            ping_delay,
            messages_queue,
            save_messages_queue,
            status_updates_queue,
            watchdog_queue,
        )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except InvalidToken:
        pass
