import json
import socket
import asyncio
import logging
from time import time

import websockets

from .util import Queue, get as default_get
from .error import (
    SocketIOError, ConnectionFailed,
    ConnectionClosed, PingTimeout
)
from .proxy import ProxyError


class SocketIO:
    """Asynchronous socket.io connection.

    Attributes
    ----------
    websocket : `websockets.client.WebSocketClientProtocol`
        Websocket connection.
    ping_interval : `float`
        Ping interval in seconds.
    ping_timeout : `float`
        Ping timeout in seconds.
    error : `None` or `Exception`
    events : `asyncio.Queue` of ((`str`, `object`) or `None`)
        Event queue.
    response : `dict` of (`str`, `asyncio.Future`)
        (event, response future)
    ping_task : `asyncio.tasks.Task`
    recv_task : `asyncio.tasks.Task`
    closing : `asyncio.Event`
    closed : `asyncio.Event`
    ping_response : `asyncio.Event`
    loop : `asyncio.events.AbstractEventLoop`
        Event loop.
    """

    logger = logging.getLogger(__name__)

    def __init__(self, websocket, config, qsize, loop):
        """
        Parameters
        ----------
        websocket : `websockets.client.WebSocketClientProtocol`
            Websocket connection.
        config : `dict`
            Websocket configuration.
        qsize : `int`
            Event queue size.
        loop : `asyncio.events.AbstractEventLoop`
            Event loop.
        """
        self.websocket = websocket
        self.loop = loop
        self._error = None
        self.closing = asyncio.Event(loop=self.loop)
        self.closed = asyncio.Event(loop=self.loop)
        self.ping_response = asyncio.Event(loop=self.loop)
        self.events = Queue(maxsize=qsize, loop=self.loop)
        self.response = {}
        self.ping_interval = max(1, config.get('pingInterval', 10000) / 1000)
        self.ping_timeout = max(1, config.get('pingTimeout', 10000) / 1000)
        self.ping_task = self.loop.create_task(self._ping())
        self.recv_task = self.loop.create_task(self._recv())

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, ex):
        if self._error is None:
            self.logger.info('set error %r', ex)
            self._error = ex
        else:
            self.logger.info('error already set: %r', self._error)
        self.logger.info('queue null event')
        try:
            self.events.put_nowait(None)
        except asyncio.QueueFull:
            pass

    @asyncio.coroutine
    def close(self):
        """Close the connection.
        """
        self.logger.info('close')

        if self.closed.is_set():
            self.logger.info('already closed')
            return

        if self.closing.is_set():
            self.logger.info('already closing, wait')
            yield from self.closed.wait()
            return

        self.closing.set()

        try:
            self.logger.info('set error')
            self.error = ConnectionClosed()

            self.logger.info('cancel ping task')
            self.ping_task.cancel()
            yield from asyncio.wait_for(self.ping_task, None, loop=self.loop)

            self.ping_response.clear()

            self.logger.info('cancel recv task')
            self.recv_task.cancel()
            yield from asyncio.wait_for(self.recv_task, None, loop=self.loop)

            self.logger.info('close websocket')
            yield from self.websocket.close()

            self.logger.info('clear event queue')
            while not self.events.empty():
                ev = yield from self.events.get()
                self.events.task_done()
                if isinstance(ev, Exception):
                    self.error = ev
            #yield from self.events.join()

            self.logger.info('cancel response futures')
            for res in self.response.values():
                if not res.done():
                    res.cancel()
            self.response = {}
        finally:
            self.ping_task = None
            self.recv_task = None
            self.websocket = None
            self.closed.set()

    @asyncio.coroutine
    def recv(self):
        """Receive an event.

        Returns
        -------
        (`str`, `object`)
            Event name and data.

        Raises
        ------
        `ConnectionClosed`
        """
        if self.error is not None:
            raise self.error # pylint:disable=raising-bad-type
        ev = yield from self.events.get()
        self.events.task_done()
        if ev is None:
            raise self.error # pylint:disable=raising-bad-type
        return ev

    @asyncio.coroutine
    def emit(self, event, data, get_response=False, timeout=None):
        """Send an event.

        Parameters
        ----------
        event : `str`
            Event name.
        data : `object`
            Event data.
        get_response : `bool` or `str`, optional
        timeout : `float` or `None`, optional

        Returns
        -------
        `object`
            Response data if `get_response` is `True`.

        Raises
        ------
        `asyncio.CancelledError`
        `SocketIOError`
        """
        data = '42%s' % json.dumps((event, data))
        self.logger.info('emit %s', data)
        try:
            if get_response:
                if isinstance(get_response, str):
                    response_event = get_response
                else:
                    response_event = event
                if response_event in self.response:
                    raise SocketIOError(
                        'already waiting for "%s" response' % response_event
                    )
                self.logger.info('get response %s', data)
                res = asyncio.Future(loop=self.loop)
                self.response[response_event] = res

            yield from self.websocket.send(data)

            if get_response:
                if timeout is not None:
                    res = asyncio.wait_for(res, timeout, loop=self.loop)
                try:
                    res = yield from res
                    self.logger.info('%s', self.response)
                except asyncio.CancelledError:
                    self.logger.info('response cancelled %s', response_event)
                    del self.response[response_event]
                    raise
                except asyncio.TimeoutError:
                    self.logger.info('response timeout %s', response_event)
                    self.response[response_event].cancel()
                    del self.response[response_event]
                    res = None
                self.logger.info('response %s %s', response_event, res)
                return res
        except Exception as ex:
            self.logger.error('emit error: %r', ex)
            if not isinstance(ex, (SocketIOError, asyncio.CancelledError)):
                ex = SocketIOError(ex)
            raise ex

    @asyncio.coroutine
    def _ping(self):
        """Ping task."""
        try:
            dt = 0
            while self.error is None:
                yield from asyncio.sleep(max(self.ping_interval - dt, 0))
                self.logger.debug('ping')
                self.ping_response.clear()
                dt = time()
                yield from self.websocket.send('2')
                yield from asyncio.wait_for(
                    self.ping_response.wait(),
                    self.ping_timeout,
                    loop=self.loop
                )
                dt = max(time() - dt, 0)
        except asyncio.CancelledError:
            self.logger.info('ping cancelled')
        except asyncio.TimeoutError:
            self.logger.error('ping timeout')
            self.error = PingTimeout()
        except (socket.error,
                ProxyError,
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.InvalidState,
                websockets.exceptions.PayloadTooBig,
                websockets.exceptions.WebSocketProtocolError
               ) as ex:
            self.logger.error('ping error: %r', ex)
            self.error = ConnectionClosed(ex)

    @asyncio.coroutine
    def _recv(self):
        """Read task."""
        try:
            while self.error is None:
                data = yield from self.websocket.recv()
                self.logger.debug('recv %s', data)
                if data.startswith('2'):
                    data = data[1:]
                    self.logger.debug('ping %s', data)
                    yield from self.websocket.send('3' + data)
                elif data.startswith('3'):
                    self.logger.debug('pong %s', data[1:])
                    self.ping_response.set()
                elif data.startswith('42'):
                    try:
                        data = json.loads(data[2:])
                        if not isinstance(data, list):
                            raise ValueError('not an array')
                        if len(data) == 0:
                            raise ValueError('empty array')
                        if len(data) == 1:
                            event, data = data[0], None
                        elif len(data) == 2:
                            event, data = data
                        else:
                            event = data[0]
                            data = data[1:]
                    except ValueError as ex:
                        self.logger.error('invalid event %s: %r', data, ex)
                    else:
                        self.logger.debug('event %s %s', event, data)
                        if event in self.response:
                            self.logger.debug('response %s %s', event, data)
                            self.response[event].set_result(data)
                            del self.response[event]
                        else:
                            yield from self.events.put((event, data))
                else:
                    self.logger.warning('unknown event: "%s"', data)
        except asyncio.CancelledError:
            self.logger.info('recv cancelled')
            self.error = ConnectionClosed()
        except (socket.error,
                ProxyError,
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.InvalidState,
                websockets.exceptions.PayloadTooBig,
                websockets.exceptions.WebSocketProtocolError
               ) as ex:
            self.logger.error('recv error: %r', ex)
            self.error = ConnectionClosed(ex)
        except Exception as ex:
            self.error = ConnectionClosed(ex)
            raise

    @classmethod
    def _get_config(cls, url, loop, get):
        """Get socket configuration.

        Parameters
        ----------
        url : `str`
        get : `function`

        Returns
        -------
        `dict`
            Socket id, ping timeout, ping interval.
        """
        url = url + '?EID=2&transport=polling'
        cls.logger.info('get %s', url)
        data = yield from get(url, loop=loop)
        try:
            data = json.loads(data[data.index('{'):])
            if 'sid' not in data:
                raise ValueError('no sid in %s' % data)
        except ValueError:
            raise websockets.exceptions.InvalidHandshake(data)
        return data

    @classmethod
    @asyncio.coroutine
    def _connect(cls, url, qsize, loop, get, connect):
        """Create a connection.

        Parameters
        ----------
        url : `str`
        qsize : `int`
        loop : `asyncio.events.AbstractEventLoop`
        get : `function`
        connect : `function`

        Returns
        -------
        `SocketIO`
        """
        conf = yield from cls._get_config(url, loop, get)
        sid = conf['sid']
        cls.logger.info('sid=%s', sid)
        url = '%s?EID=3&transport=websocket&sid=%s' % (
            url.replace('http', 'ws', 1), sid
        )
        cls.logger.info('connect %s', url)
        websocket = yield from connect(url, loop=loop)
        try:
            cls.logger.info('2probe')
            yield from websocket.send('2probe')
            res = yield from websocket.recv()
            cls.logger.info('3probe')
            if res != '3probe':
                raise websockets.exceptions.InvalidHandshake(
                    'invalid response: "%s" != "3probe"',
                    res
                )
            cls.logger.info('upgrade')
            yield from websocket.send('5')
            return SocketIO(websocket, conf, qsize, loop)
        except:
            yield from websocket.close()
            raise

    @classmethod
    @asyncio.coroutine
    def connect(cls,
                url,
                retry=-1,
                retry_delay=1,
                qsize=0,
                loop=None,
                get=default_get,
                connect=websockets.connect):
        """Create a connection.

        Parameters
        ----------
        url : `str`
            socket.io URL.
        retry : `int`
            Maximum number of tries.
        retry_delay : `float`
            Delay between tries in seconds.
        qsize : `int`
            Event queue size.
        loop : `None` or `asyncio.events.AbstractEventLoop`
            Event loop.
        get : `function`
            HTTP GET request coroutine.
        connect : `function`
            Websocket connect coroutine.

        Returns
        -------
        `SocketIO`

        Raises
        ------
        `ConnectionFailed`
        """
        loop = loop or asyncio.get_event_loop()
        i = 0
        while True:
            try:
                io = yield from cls._connect(url, qsize, loop, get, connect)
                return io
            except Exception as ex:
                cls.logger.error(
                    'connect(%s) (try %d / %d): %r',
                    url, i + 1, retry + 1, ex
                )
                if i == retry:
                    raise ConnectionFailed(ex)
            i += 1
            yield from asyncio.sleep(retry_delay)
