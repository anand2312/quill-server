from argparse import ArgumentParser
import asyncio
import signal

import websockets
from loguru import logger


parser = ArgumentParser("Quill CLI Client")
parser.add_argument("--host", default="127.0.0.1:8000")
parser.add_argument("-t", "--token")
parser.add_argument("room")

args = parser.parse_args()


async def ws_connect() -> None:
    async with websockets.connect(
        "ws://" + args.host + f"/room/{args.room}",
        extra_headers={"Authorization": f"Bearer {args.token}"},
    ) as ws:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, loop.create_task, ws.close())
        async for message in ws:
            logger.info(message)


asyncio.run(ws_connect())
