import re
import json
import logging
import asyncio
import collections

from .error import (
    SocketConfigError, LoginError,
    ChannelError, ChannelPermissionError, Kicked
)
from .socket_io import SocketIO, SocketIOError
from .channel import Channel
from .user import User
from .playlist import PlaylistItem
from .util import get as default_get, to_sequence


class Bot:
    """CyTube bot.

    Attributes
    ----------
    get : `function` (url, loop)
        HTTP GET coroutine.
    socket_io : `function` (url, loop)
        socket.io connect coroutine.
    response_timeout : `float`
        socket.io event response timeout in seconds.
    restart_delay : `None` or `float`
        Delay in seconds before reconnection.
        `None` or < 0 - do not reconnect.
    domain : `str`
        Domain.
    channel : `cytube_bot.channel.Channel`
        Channel.
    user : `cytube_bot.user.User`
        Bot user.
    loop : `asyncio.events.AbstractEventLoop`
        Event loop.
    server : `None` or `str`
        socket.io server URL.
    socket : `None` or `cytube_bot.socket_io.SocketIO`
        socket.io connection.
    handlers : `collections.defaultdict` of (`str`, `list` of `function`)
        Event handlers.
    """
    logger = logging.getLogger(__name__)

    SOCKET_CONFIG_URL = '%(domain)s/socketconfig/%(channel)s.json'
    SOCKET_IO_URL = '%(domain)s/socket.io/'

    GUEST_LOGIN_LIMIT = re.compile(r'guest logins .* ([0-9]+) seconds\.', re.I)
    MUTED = re.compile(r'.*\bmuted', re.I)

    EVENT_LOG_LEVEL = {
        'mediaUpdate': logging.DEBUG,
        'channelCSSJS': logging.DEBUG,
        'emoteList': logging.DEBUG
    }

    EVENT_LOG_LEVEL_DEFAULT = logging.INFO

    def __init__(self, domain,
                 channel, user=None,
                 restart_delay=5,
                 loop=None,
                 response_timeout=0.1,
                 get=default_get,
                 socket_io=SocketIO.connect):
        """
        Parameters
        ----------
        domain : `str`
            Domain.
        channel : `str` or (`str`, `str`)
            'name' or ('name', 'password')
        user : `None` or `str` or (`str`, `str`), optional
            `None` (anonymous) or 'name' (guest) or ('name', 'password') (registered)
        restart_delay : `None` or `float`, optional
            Delay in seconds before reconnection.
            `None` or < 0 - do not reconnect.
        loop : `asyncio.events.AbstractEventLoop`, optional
            Event loop.
        response_timeout : `float`, optional
            socket.io event response timeout in seconds.
        get : `function` (url, loop), optional
            HTTP GET coroutine.
        socket_io : `function` (url, loop), optional
            socket.io connect coroutine.
        """
        self.get = get
        self.socket_io = socket_io
        self.response_timeout = response_timeout
        self.restart_delay = restart_delay
        self.domain = domain
        self.channel = Channel(*to_sequence(channel))
        self.user = User(*to_sequence(user))
        self.loop = loop or asyncio.get_event_loop()
        self.server = None
        self.socket = None
        self.handlers = collections.defaultdict(list)
        for attr in dir(self):
            if attr.startswith('_on_'):
                self.on(attr[4:], getattr(self, attr))

    def _on_rank(self, _, data):
        self.user.rank = data

    def _on_setMotd(self, _, data):
        self.channel.motd = data

    def _on_channelCSSJS(self, _, data):
        self.channel.css = data.get('css', '')
        self.channel.js = data.get('js', '')

    def _on_channelOpts(self, _, data):
        self.channel.options = data

    def _on_setPermissions(self, _, data):
        self.channel.permissions = data

    def _on_emoteList(self, _, data):
        self.channel.emotes = data

    def _on_drinkCount(self, _, data):
        self.channel.drink_count = data

    def _on_usercount(self, _, data):
        self.channel.userlist.count = data

    @staticmethod
    def _on_needPassword(_, data):
        if data:
            raise LoginError('invalid channel password')

    def _on_noflood(self, _, data):
        self.loger.error('noflood: %r', data)

    def _on_errorMsg(self, _, data):
        self.logger.error('error: %r', data)

    def _on_queueFail(self, _, data):
        self.logger.error('playlist error: %r', data)

    @staticmethod
    def _on_kick(_, data):
        raise Kicked(data)

    def _add_user(self, data):
        if data['name'] == self.user.name:
            self.user.update(**data)
            self.channel.userlist.add(self.user)
        else:
            self.channel.userlist.add(User(**data))

    def _on_userlist(self, _, data):
        self.channel.userlist.clear()
        for user in data:
            self._add_user(user)
        self.logger.info('userlist: %s', self.channel.userlist)

    def _on_addUser(self, _, data):
        self._add_user(data)
        self.logger.info('userlist: %s', self.channel.userlist)

    def _on_userLeave(self, _, data):
        user = data['name']
        try:
            del self.channel.userlist[user]
        except KeyError:
            self.logger.error('userLeave: %s not found', user)
        self.logger.info('userlist: %s', self.channel.userlist)

    def _on_setUserMeta(self, _, data):
        self.channel.userlist[data['name']].meta = data['meta']

    def _on_setUserRank(self, _, data):
        self.channel.userlist[data['name']].rank = data['rank']

    def _on_setAFK(self, _, data):
        self.channel.userlist[data['name']].afk = data['afk']

    def _on_setLeader(self, _, data):
        self.channel.userlist.leader = data
        self.logger.info('leader %r', self.channel.userlist.leader)

    def _on_setPlaylistMeta(self, _, data):
        self.channel.playlist.time = data.get('rawTime', 0)

    def _on_mediaUpdate(self, _, data):
        self.channel.playlist.paused = data.get('paused', True)
        self.channel.playlist.current_time = data.get('currentTime', 0)

    def _on_voteskip(self, _, data):
        self.channel.voteskip_count = data.get('count', 0)
        self.channel.voteskip_need = data.get('need', 0)
        self.logger.info(
            'voteskip %s / %s',
            self.channel.voteskip_count,
            self.channel.voteskip_need
        )

    def _on_setCurrent(self, _, data):
        self.channel.playlist.current = data
        self.logger.info('setCurrent %s', self.channel.playlist.current)

    def _on_queue(self, _, data):
        self.channel.playlist.add(data['after'], data['item'])
        self.logger.info('queue %s', self.channel.playlist.queue)

    def _on_delete(self, _, data):
        self.channel.playlist.remove(data['uid'])
        self.logger.info('delete %s', self.channel.playlist.queue)

    def _on_setTemp(self, _, data):
        self.channel.playlist.get(data['uid']).temp = data['temp']

    def _on_moveVideo(self, _, data):
        self.channel.playlist.move(data['from'], data['after'])
        self.logger.info('move %s', self.channel.playlist.queue)

    def _on_playlist(self, _, data):
        self.channel.playlist.clear()
        for item in data:
            self.channel.playlist.add(None, item)
        self.logger.info('playlist %s', self.channel.playlist.queue)

    def _on_setPlaylistLocked(self, _, data):
        self.channel.playlist.locked = data
        self.logger.info('playlist locked %s', data)

    @asyncio.coroutine
    def get_socket_config(self):
        """Get server URL.

        Raises
        ------
        cytube_bot.error.SocketConfigError
        """
        data = {
            'domain': self.domain,
            'channel': self.channel.name
        }
        url = self.SOCKET_CONFIG_URL % data
        if not url.startswith('http'):
            url = 'https://' + url
        self.logger.info('get_socket_config %s', url)
        conf = yield from self.get(url, loop=self.loop)
        conf = json.loads(conf)
        self.logger.info(conf)
        if 'error' in conf:
            raise SocketConfigError(conf['error'])
        try:
            server = next(
                srv['url']
                for srv in conf['servers']
                if srv['secure']
            )
            self.logger.info('secure server %s', server)
        except (KeyError, StopIteration):
            self.logger.info('no secure servers')
            try:
                server = next(srv['url'] for srv in conf['servers'])
                self.logger.info('server %s', server)
            except (KeyError, StopIteration):
                self.logger.info('no servers')
                raise SocketConfigError('no servers in socket config', conf)
        data['domain'] = server
        self.server = self.SOCKET_IO_URL % data

    @asyncio.coroutine
    def disconnect(self):
        """Disconnect.
        """
        if self.socket is None:
            return
        self.logger.info('disconnect %s', self.server)
        try:
            yield from self.socket.close()
        except Exception as ex:
            self.logger.error('socket.close(): %s: %r', self.server, ex)
            raise
        finally:
            self.socket = None
            self.user.rank = -1

    @asyncio.coroutine
    def connect(self):
        """Get server URL and connect.

        Raises
        ------
        `cytube_bot.error.SocketIOError`
        """
        yield from self.disconnect()
        if self.server is None:
            yield from self.get_socket_config()
        self.logger.info('connect %s', self.server)
        self.socket = yield from self.socket_io(self.server, loop=self.loop)

    @asyncio.coroutine
    def login(self):
        """Connect, join channel, log in.

        Raises
        ------
        `cytube_bot.error.LoginError`
        `cytube_bot.error.SocketIOError`
        """
        yield from self.connect()

        self.logger.info('join channel %s', self.channel)
        res = yield from self.socket.emit(
            'joinChannel',
            {
                'name': self.channel.name,
                'pw': self.channel.password
            },
            'needPassword',
            self.response_timeout
        )
        if res:
            raise LoginError('invalid channel password')

        if not self.user.name:
            self.logger.warning('no user')
        else:
            while True:
                self.logger.info('login %s', self.user)
                res = yield from self.socket.emit(
                    'login',
                    {
                        'name': self.user.name,
                        'pw': self.user.password
                    },
                    True
                )
                self.logger.info('login %s', res)
                if res.get('success', False):
                    break
                err = res.get('error', '<no error message>')
                self.logger.error('login error: %s', res)
                match = self.GUEST_LOGIN_LIMIT.match(err)
                if match:
                    try:
                        delay = max(int(match.group(1)), 1)
                        self.logger.warning('sleep(%d)', delay)
                        yield from asyncio.sleep(delay)
                    except ValueError:
                        raise LoginError(err)
                else:
                    raise LoginError(err)
        yield from self.trigger('login', self)

    @asyncio.coroutine
    def run(self):
        """Main loop.
        """
        try:
            yield from self.login()
            self.logger.info('start')
            while True:
                try:
                    ev, data = yield from self.socket.recv()
                except SocketIOError as ex:
                    self.logger.error('network error: %r', ex)
                    if self.restart_delay is None or self.restart_delay < 0:
                        break
                    self.logger.error('restarting')
                    yield from asyncio.sleep(self.restart_delay)
                    yield from self.login()
                else:
                    yield from self.trigger(ev, data)
        except asyncio.CancelledError:
            self.logger.info('cancelled')
        finally:
            yield from self.disconnect()

    def on(self, event, *handlers):
        """Add event handlers.

        Parameters
        ----------
        event : `str`
            Event name.
        handlers : `list` of `function`
            Event handlers.
        """
        ev_handlers = self.handlers[event]
        for handler in handlers:
            if handler not in ev_handlers:
                ev_handlers.append(handler)
                self.logger.info('on: %s %s', event, handler)
            else:
                self.logger.warning('on: handler exists: %s %s', event, handler)
        return self

    def off(self, event, *handlers):
        """Remove event handlers.

        Parameters
        ----------
        event : `str`
            Event name.
        handlers : `list` of `function`
            Event handlers.
        """
        ev_handlers = self.handlers[event]
        for handler in handlers:
            try:
                ev_handlers.remove(handler)
                self.logger.info('off: %s %s', event, handler)
            except ValueError:
                self.logger.warning(
                    'off: handler not found: %s %s',
                    event, handler
                )
        return self

    @asyncio.coroutine
    def trigger(self, event, data):
        """Trigger an event.

        Parameters
        ----------
        event : `str`
            Event name.
        data : `object`
            Event data.

        Raises
        ------
        `cytube_bot.error.LoginError`
        `cytube_bot.error.Kicked`
        """
        level = self.EVENT_LOG_LEVEL.get(event, self.EVENT_LOG_LEVEL_DEFAULT)
        self.logger.log(level, 'trigger: %s %s', event, data)
        try:
            for handler in self.handlers[event]:
                if asyncio.iscoroutinefunction(handler):
                    stop = yield from handler(event, data)
                else:
                    stop = handler(event, data)
                if stop:
                    break
        except (asyncio.CancelledError, LoginError, Kicked):
            raise
        except Exception as ex:
            self.logger.error('trigger %s %s: %r', event, data, ex)
            if event != 'error':
                yield from self.trigger('error', {
                    'event': event,
                    'data': data,
                    'error': ex
                })

    @asyncio.coroutine
    def chat(self, msg, meta=None):
        """Send a chat message.

        Parameters
        ----------
        msg : `str`
        meta : `None` or `dict`, optional

        Raises
        ------
        cytube_bot.error.ChannelPermissionError
        """
        self.logger.info('chat %s', msg)
        self.channel.check_permission('chat', self.user)

        if self.user.muted or self.user.smuted:
            raise ChannelPermissionError('muted')

        res = yield from self.socket.emit(
            'chatMsg',
            {'msg': msg, 'meta': meta if meta else {}},
            'noflood',
            self.response_timeout
        )
        if res is not None:
            self.logger.error('chat: noflood: %s', res)
            raise ChannelPermissionError(res.get('msg', 'noflood'))
            #if self.MUTED.match(res['msg']):
            #    raise ChannelPermissionError('muted')

    @asyncio.coroutine
    def pm(self, to, msg, meta=None):
        """Send a private chat message.

        Parameters
        ----------
        to : `str`
        msg : `str`
        meta : `None` or `dict`, optional

        Raises
        ------
        cytube_bot.error.ChannelPermissionError
        cytube_bot.error.ChannelError
        """
        self.logger.info('pm %s %s', to, msg)
        self.channel.check_permission('chat', self.user)

        if self.user.muted or self.user.smuted:
            raise ChannelPermissionError('muted')

        res = yield from self.socket.emit(
            'pm',
            {'msg': msg, 'to': to, 'meta': meta if meta else {}},
            'errorMsg',
            self.response_timeout
        )
        if res is not None:
            self.logger.error('pm: %r', res)
            raise ChannelError(res.get('msg', '<no message>'))

    @asyncio.coroutine
    def set_afk(self, value=True):
        """Set bot AFK.

        Parameters
        ----------
        value : `bool`, optional

        Raises
        ------
        cytube_bot.error.ChannelPermissionError
        """
        if self.user.afk != value:
            yield from self.chat('/afk')

    @asyncio.coroutine
    def clear_chat(self):
        """Clear chat.

        Raises
        ------
        cytube_bot.error.ChannelPermissionError
        """
        self.channel.check_permission('chatclear', self.user)
        yield from self.chat('/clear')

    @asyncio.coroutine
    def add_media(self, link, append=True, temp=True):
        """Add media link to playlist.

        Parameters
        ----------
        link : `cytube_bot.media_link.MediaLink`
            Media link.
        append : `bool`, optional
            `True` - append, `False` - insert after current item.
        temp : `bool`, optional
            `True` to add temporary item.

        Raises
        ------
        cytube_bot.error.ChannelPermissionError
        cytube_bot.error.ChannelError
        """
        action = 'playlist' if self.channel.playlist.locked else 'oplaylist'
        self.logger.info('add media %s', link)
        self.channel.check_permission(action + 'add', self.user)
        if not append:
            self.channel.check_permission(action + 'next', self.user)
        if not temp:
            self.channel.check_permission('addnontemp', self.user)

        res = yield from self.socket.emit(
            'queue',
            {
                'type': link.type,
                'id': link.id,
                'pos': 'end' if append else 'next',
                'temp': temp
            },
            'queueFail',
            self.response_timeout
        )

        if res is not None:
            self.logger.info('queueFail %r', res)
            raise ChannelError(res.get('msg', '<no message>'))

    @asyncio.coroutine
    def remove_media(self, item):
        """Remove playlist item.

        Parameters
        ----------
        item: `int` or `cytube_bot.playlist.PlaylistItem`
            Item to remove.

        Raises
        ------
        cytube_bot.error.ChannelPermissionError
        """
        if self.channel.playlist.locked:
            action = 'playlistdelete'
        else:
            action = 'oplaylistdelete'
        self.channel.check_permission(action, self.user)
        if not isinstance(item, PlaylistItem):
            item = self.playlist.get(item)
        yield from self.socket.emit('delete', item.uid)
