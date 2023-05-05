import asyncio
import logging
from datetime import datetime

from async_timeout import timeout

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


async def watch_for_connection(watchdog_queue):
    while True:
        try:
            async with timeout(1) as cm:
                message = await watchdog_queue.get()
                message = f'[{datetime.now().timestamp()}] Connection is alive. {message}'
                watchdog_logger.info(message)
        except asyncio.exceptions.TimeoutError:
            watchdog_logger.info(f'[{datetime.now().timestamp()}] 1s timeout is elapsed')


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

    await asyncio.gather(
        read_messages(
            chat_host,
            chat_port_listen,
            messages_queue,
            save_messages_queue,
            status_updates_queue,
            watchdog_queue,
        ),
        save_messages(history_path, save_messages_queue),
        gui.draw(messages_queue, sending_queue, status_updates_queue),
        handle_message_sending(
            chat_host,
            chat_port_write,
            user_token,
            messages_queue,
            sending_queue,
            status_updates_queue,
            watchdog_queue,
        ),
        watch_for_connection(watchdog_queue),
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except InvalidToken:
        pass
