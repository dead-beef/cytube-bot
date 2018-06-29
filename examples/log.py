#!/usr/bin/env python3

import sys
import logging
import asyncio
from functools import partial
from time import localtime, strftime

from cytube_bot import Bot
from cytube_bot.error import CytubeError, SocketIOError

from util import get_config, configure_logger


def log_chat(logger, event, data):
    time = data.get('time', 0)
    time = strftime('%d/%m/%Y %H:%m:%S', localtime(time))
    user = data.get('username', '<no username>')
    msg = data.get('msg', '<no message>')
    if event == 'pm':
        logger.info(
            '[%s] %s -> %s: %s',
            time, user, data.get('to', '<no username>'), msg
        )
    else:
        logger.info('[%s] %s: %s', time, user, msg)

def log_video(bot, logger, *_):
    current = bot.channel.playlist.current
    if current is not None:
        logger.info(
            '%s: %s %s "%s"',
            current.username, current.type, current.id, current.title
        )

def main():
    conf, kwargs = get_config()
    loop = asyncio.get_event_loop()

    chat_logger = logging.getLogger('chat')
    video_logger = logging.getLogger('video')
    configure_logger(
        chat_logger,
        log_file=conf.get('chat_log_file', None),
        log_format='%(message)s'
    )
    configure_logger(
        video_logger,
        log_file=conf.get('video_log_file', None),
        log_format='[%(asctime).19s] %(message)s'
    )

    bot = Bot(loop=loop, **kwargs)

    log = partial(log_chat, chat_logger)
    log_v = partial(log_video, bot, video_logger)

    bot.on('chatMsg', log)
    bot.on('pm', log)
    bot.on('setCurrent', log_v)

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
