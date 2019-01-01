#!/usr/bin/env python3

import sys
import asyncio

from cytube_bot import Bot, MessageParser
from cytube_bot.error import CytubeError, SocketIOError

from examples.config import get_config


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
    shell = Shell(conf.get('shell', None), bot, loop=loop)

    try:
        task = loop.create_task(bot.run())
        if shell.task is not None:
            task_ = asyncio.gather(task, shell.task)
        else:
            task_ = task
        loop.run_until_complete(task_)
    except (CytubeError, SocketIOError) as ex:
        print(repr(ex), file=sys.stderr)
    except KeyboardInterrupt:
        return 0
    finally:
        task_.cancel()
        task.cancel()
        shell.close()
        loop.run_until_complete(task)
        if shell.task is not None:
            loop.run_until_complete(shell.task)
        loop.close()

    return 1


if __name__ == '__main__':
    sys.exit(main())
