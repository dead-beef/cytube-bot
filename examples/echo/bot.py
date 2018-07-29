#!/usr/bin/env python3

import sys
import asyncio

from cytube_bot import Bot
from cytube_bot.error import CytubeError, SocketIOError

from examples.util import get_config, MessageParser


class EchoBot(Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.msg_parser = MessageParser()
        self.on('chatMsg', self.echo)
        self.on('pm', self.echo)

    @asyncio.coroutine
    def echo(self, event, data):
        username = data['username']
        if username == self.user.name or self.user.rank < 0:
            return
        msg = self.msg_parser.parse(data['msg'])
        if event == 'pm':
            yield from self.pm(data['username'], msg)
        elif msg.startswith(self.user.name):
            yield from self.chat(msg.replace(self.user.name, username, 1))


def main():
    _, kwargs = get_config()
    loop = asyncio.get_event_loop()

    bot = EchoBot(loop=loop, **kwargs)

    try:
        task = loop.create_task(bot.run())
        loop.run_until_complete(task)
    except (CytubeError, SocketIOError) as ex:
        print(repr(ex), file=sys.stderr)
    except KeyboardInterrupt:
        task.cancel()
        loop.run_forever()
        return 0
    finally:
        loop.close()

    return 1


if __name__ == '__main__':
    sys.exit(main())
