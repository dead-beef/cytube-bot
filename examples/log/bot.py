#!/usr/bin/env python3

import sys
import logging
import asyncio
from functools import partial
from time import localtime, strftime

from cytube_bot import Bot
from cytube_bot.error import CytubeError, SocketIOError

from examples.util import get_config, configure_logger


def log_chat(logger, event, data):
    time = data.get('time', 0)
    time = strftime('%d/%m/%Y %H:%m:%S', localtime(time // 1000))
    user = data.get('username', '<no username>')
    msg = data.get('msg', '<no message>')
    if event == 'pm':
        logger.info(
            '[%s] %s -> %s: %s',
            time, user, data.get('to', '<no username>'), msg
        )
    else:
        logger.info('[%s] %s: %s', time, user, msg)

def log_media(bot, logger, *_):
    current = bot.channel.playlist.current
    if current is not None:
        logger.info(
            '%s: %s "%s"',
            current.username, current.link.url, current.title
        )

def main():
    conf, kwargs = get_config()
    loop = asyncio.get_event_loop()

    chat_logger = logging.getLogger('chat')
    media_logger = logging.getLogger('media')
    configure_logger(
        chat_logger,
        log_file=conf.get('chat_log_file', None),
        log_format='%(message)s'
    )
    configure_logger(
        media_logger,
        log_file=conf.get('media_log_file', None),
        log_format='[%(asctime).19s] %(message)s'
    )

    bot = Bot(loop=loop, **kwargs)

    log = partial(log_chat, chat_logger)
    log_m = partial(log_media, bot, media_logger)

    bot.on('chatMsg', log)
    bot.on('pm', log)
    bot.on('setCurrent', log_m)

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
