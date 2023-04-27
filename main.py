import asyncio
import logging

import gui
import time

from chat_tools import read_messages, get_arguments, get_token

logger = logging.getLogger(__name__)


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

    await asyncio.gather(
        read_messages(chat_host, chat_port_listen, history_path, messages_queue),
        gui.draw(messages_queue, sending_queue, status_updates_queue),
    )


if __name__ == '__main__':

    asyncio.run(main())
