#!/usr/bin/env python3

import re
import sys
import logging
import asyncio
from time import localtime, strftime

from markovchain import SqliteStorage
from markovchain.text import MarkovText, ReplyMode

from cytube_bot import Bot
from cytube_bot.error import CytubeError, SocketIOError

from examples.util import get_config, configure_logger, MessageParser


class MarkovBot(Bot):
    HELP = [
        'commands:',
        '!help',
        '!settings',
        '!setorder <order>',
        '!setlearn <true|false>',
        '!settrigger <regexp>',
        '!echo <text>',
        '!markov [start]',
        '!rmarkov [end]'
    ]

    LINK = re.compile(r'\bhttps?://\S+', re.I)

    def __init__(self, markov, chat_logger, media_logger,
                 *args, order=None, learn=False, **kwargs):
        super().__init__(*args, **kwargs)
        name = re.escape(self.user.name)
        self.trigger_expr = re.compile(name, re.I)
        self.user_name_expr = re.compile(r'\b%s(:|\b)' % name, re.I)
        self.markov = markov
        self.markov_order = order
        self.learn_enabled = learn
        self.max_length = 200
        self.chat_parser = MessageParser()
        self.chat_logger = chat_logger
        self.media_logger = media_logger
        self.on(
            'chatMsg',
            self.parse_chat,
            self.log_chat,
            self.ignore,
            self.command,
            self.reply,
            self.learn
        )
        self.on(
            'pm',
            self.parse_chat,
            self.log_chat,
            self.ignore,
            self.reply,
            self.learn
        )
        self.on('setCurrent', self.log_media)

    def normalize(self, msg):
        msg = self.user_name_expr.sub('', msg)
        msg = self.LINK.sub('', msg)
        return msg.strip()

    def parse_chat(self, _, data):
        msg = self.chat_parser.parse(data.get('msg', '&lt;no message&gt;'))
        data['msg'] = msg
        data['normalized_msg'] = self.normalize(msg)

    def log_chat(self, ev, data):
        time = data.get('time', 0)
        time = strftime('%d/%m/%Y %H:%m:%S', localtime(time // 1000))
        user = data.get('username', '<no username>')
        msg = data.get('msg', '<no message>')
        if ev == 'pm':
            to = data.get('to', '<no username>')
            self.chat_logger.info('[%s] %s -> %s: %s', time, user, to, msg)
        else:
            self.chat_logger.info('[%s] %s: %s', time, user, msg)

    def log_media(self, *_):
        current = self.channel.playlist.current
        if current is not None:
            self.media_logger.info(
                '%s: %s "%s"',
                current.username, current.link.url, current.title
            )

    def ignore(self, _, data):
        if self.user == data['username']:
            self.logger.info('ignore self')
            return True
        if data['username'] == '[server]':
            self.logger.info('ignore server')
            return True
        if self.user.rank < 0:
            self.logger.info('ignore history')
            return True
        return False

    @asyncio.coroutine
    def _reply(self, ev, username, msg):
        if ev == 'pm':
            yield from self.pm(username, msg)
        else:
            yield from self.chat('%s: %s' % (username, msg))

    @asyncio.coroutine
    def reply(self, ev, data):
        msg = data['msg']
        if ev != 'pm' and not self.trigger_expr.search(msg):
            return
        msg = data['normalized_msg']
        #if not msg:
        #    self.logger.info('empty message "%s"', data['msg'])
        #    return
        self.logger.info('reply %r %s', msg, data)
        msg = self.markov(
            max_length=self.max_length,
            state_size=self.markov_order,
            reply_to=msg,
            reply_mode=ReplyMode.REPLY
        )
        yield from self._reply(ev, data['username'], msg)

    @asyncio.coroutine
    def learn(self, _, data):
        if not self.learn_enabled:
            return
        msg = data['normalized_msg']
        if msg:
            self.logger.info('learn %s', msg)
            self.markov.data(msg)
            self.markov.save()

    @asyncio.coroutine
    def command(self, _, data):
        msg = data['msg'].strip()
        if not msg.startswith('!'):
            return
        msg = msg.split(None, 1)
        if not msg:
            return

        data['cmd'] = msg[0][1:]
        if len(msg) == 1:
            data['msg'] = ''
        else:
            data['msg'] = msg[1]

        cmd = 'cmd_%s' % data['cmd']
        try:
            handler = getattr(self, cmd)
        except AttributeError:
            yield from self.chat(
                '%s: invalid command "%s"'
                % (data['username'], data['cmd'])
            )
            return True

        if asyncio.iscoroutinefunction(handler):
            yield from handler(data)
        else:
            handler(data)

        return True

    @asyncio.coroutine
    def cmd_echo(self, data):
        msg = data['msg']
        if not msg:
            msg = '%s: usage: !echo <text>' % data['username']
        yield from self.chat(msg)

    @asyncio.coroutine
    def cmd_setorder(self, data):
        msg = data['msg']
        if not msg:
            msg = '%s: usage: !setorder <order>' % data['username']
        try:
            order = int(msg)
            if order not in self.markov.parser.state_sizes:
                raise ValueError(
                    'invalid order: %s: not in %s'
                    % (order, self.markov.parser.state_sizes)
                )
            msg = '%s: order: %s -> %s' % (
                data['username'], self.markov_order, order
            )
            self.markov_order = order
        except ValueError as ex:
            msg = '%s: %r' % (data['username'], ex)
        yield from self.chat(msg)

    @asyncio.coroutine
    def cmd_setlearn(self, data):
        msg = data['msg'].lower()
        if msg in ('true', 'false'):
            learn = msg == 'true'
            msg = '%s: learn: %s -> %s' % (
                data['username'], self.learn_enabled, learn
            )
            self.learn_enabled = learn
        else:
            msg = '%s: usage: !setlearn <true|false>' % data['username']
        yield from self.chat(msg)

    @asyncio.coroutine
    def cmd_settrigger(self, data):
        msg = data['msg']
        if not msg:
            msg = '%s: usage: !settrigger <regexp>' % data['username']
        else:
            try:
                trigger = re.compile(msg, re.I)
                msg = '%s: trigger: %s -> %s' % (
                    data['username'],
                    self.trigger_expr.pattern,
                    trigger.pattern
                )
                self.trigger_expr = trigger
            except re.error as ex:
                msg = '%s: %r' % (data['username'], ex)
        yield from self.chat(msg)

    @asyncio.coroutine
    def cmd_settings(self, data):
        msg = '%s: order=%s learn=%s trigger=%s' % (
            data['username'],
            self.markov_order,
            self.learn_enabled,
            self.trigger_expr
        )
        yield from self.chat(msg)

    @asyncio.coroutine
    def cmd_help(self, _):
        for msg in self.HELP:
            yield from self.chat(msg)
            yield from asyncio.sleep(0.2)

    @asyncio.coroutine
    def _cmd_markov(self, data, reply_mode):
        msg = data['msg']
        if not msg:
            msg = self.markov(
                max_length=self.max_length,
                state_size=self.markov_order,
                reply_mode=reply_mode
            )
        else:
            msg = self.markov(
                max_length=self.max_length,
                state_size=self.markov_order,
                reply_to=msg,
                reply_mode=reply_mode
            )
        yield from self.chat('%s: %s' % (data['username'], msg))

    @asyncio.coroutine
    def cmd_markov(self, data):
        yield from self._cmd_markov(data, ReplyMode.END)

    @asyncio.coroutine
    def cmd_rmarkov(self, data):
        yield from self._cmd_markov(data, ReplyMode.START)


def main():
    conf, kwargs = get_config()
    chat_logger = logging.getLogger('chat')
    media_logger = logging.getLogger('media')
    loop = asyncio.get_event_loop()
    configure_logger(
        chat_logger,
        log_file=conf.get('chat_log_file', None),
        log_format='%(message)s',
        log_level=logging.INFO
    )
    configure_logger(
        media_logger,
        log_file=conf.get('media_log_file', None),
        log_format='[%(asctime).19s] %(message)s',
        log_level=logging.INFO
    )
    markov = MarkovText.from_file(conf['markov'], storage=SqliteStorage)
    bot = MarkovBot(
        markov, chat_logger, media_logger,
        order=conf.get('order', None),
        learn=conf.get('learn', False),
        loop=loop,
        **kwargs
    )
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
        markov.save()
        loop.close()

    return 1


if __name__ == '__main__':
    sys.exit(main())
