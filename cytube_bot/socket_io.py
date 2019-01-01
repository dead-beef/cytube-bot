import re
import json
import socket
import asyncio
import logging
from time import time

import websockets

from .util import Queue, get as default_get, current_task
from .error import (
    SocketIOError, ConnectionFailed,
    ConnectionClosed, PingTimeout
)
from .proxy import ProxyError


class SocketIOResponse:
    """socket.io event response.

    Attributes
    ----------
    id : `int`
    match : `function`(`str`, `object`)
    future : `asyncio.Future`
    """
    MAX_ID = 2 ** 32
    last_id = 0

    def __init__(self, match):
        self.id = (self.last_id + 1) % self.MAX_ID
        self.last_id = self.id
        self.match = match
        self.future = asyncio.Future()

    def __eq__(self, res):
        if isinstance(res, SocketIOResponse):
            return self is res
        return self.id == res

    def __str__(self):
        return '<SocketIOResponse #%d>' % self.id

    __repr__ = __str__

    def set(self, value):
        self.future.set_result(value)

    def cancel(self, ex=None):
        if not self.future.done():
            if ex is None:
                self.future.cancel()
            else:
                self.future.set_exception(ex)

    @staticmethod
    def match_event(ev=None, data=None):
        def match(ev_, data_):
            if not re.match(ev, ev_):
                return False
            if data is not None:
                if isinstance(data, dict):
                    if not isinstance(data_, dict):
                        return False
                    for key, value in data.items():
                        if value != data_.get(key):
                            return False
                else:
                    raise NotImplementedError('match_event !isinstance(data, dict)')
            return True
        return match


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
    response : `list` of `cytube_bot.socket_io.SocketIOResponse`
    response_lock : `asyncio.Lock`
    ping_task : `asyncio.tasks.Task`
    recv_task : `asyncio.tasks.Task`
    close_task : `asyncio.tasks.Task`
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
        self.response = []
        self.response_lock = asyncio.Lock()
        self.ping_interval = max(1, config.get('pingInterval', 10000) / 1000)
        self.ping_timeout = max(1, config.get('pingTimeout', 10000) / 1000)
        self.ping_task = self.loop.create_task(self._ping())
        self.recv_task = self.loop.create_task(self._recv())
        self.close_task = None

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, ex):
        if self._error is not None:
            self.logger.info('error already set: %r', self._error)
            return
        self.logger.info('set error %r', ex)
        self._error = ex
        if ex is not None:
            self.logger.info('create close task')
            self.close_task = self.loop.create_task(self.close())

    @asyncio.coroutine
    def close(self):
        """Close the connection.
        """
        self.logger.info('close')

        if self.close_task is not None:
            if self.close_task is current_task(self.loop):
                self.logger.info('current task is close task')
            else:
                self.logger.info('wait for close task')
                yield from asyncio.wait_for(self.close_task,
                                            None, loop=self.loop)

        if self.closed.is_set():
            self.logger.info('already closed')
            return

        if self.closing.is_set():
            self.logger.info('already closing, wait')
            yield from self.closed.wait()
            return

        self.closing.set()

        try:
            if self._error is None:
                self.logger.info('set error')
                self._error = ConnectionClosed()
            else:
                self.logger.info('error already set: %r', self._error)

            self.logger.info('queue null event')
            try:
                self.events.put_nowait(None)
            except asyncio.QueueFull:
                pass

            self.logger.info('set response future exception')
            for res in self.response:
                res.cancel(self.error)
            self.response = []

            self.logger.info('cancel ping task')
            self.ping_task.cancel()
            self.logger.info('cancel recv task')
            self.recv_task.cancel()

            self.logger.info('wait for tasks')
            yield from asyncio.wait_for(
                asyncio.gather(self.ping_task, self.recv_task),
                None, loop=self.loop
            )

            self.ping_response.clear()

            self.logger.info('close websocket')
            yield from self.websocket.close()

            self.logger.info('clear event queue')
            while not self.events.empty():
                ev = yield from self.events.get()
                self.events.task_done()
                if isinstance(ev, Exception):
                    self.error = ev
            #yield from self.events.join()
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
    def emit(self, event, data, match_response=False, response_timeout=None):
        """Send an event.

        Parameters
        ----------
        event : `str`
            Event name.
        data : `object`
            Event data.
        match_response : `function` or `None`, optional
            Response match function.
        response_timeout : `float` or `None`, optional
            Response timeout in seconds.

        Returns
        -------
        `object`
            Response data if `get_response` is `True`.

        Raises
        ------
        `asyncio.CancelledError`
        `SocketIOError`
        """
        if self.error is not None:
            raise self.error # pylint:disable=raising-bad-type
        data = '42%s' % json.dumps((event, data))
        self.logger.info('emit %s', data)
        release = False
        response = None
        try:
            if match_response is not None:
                yield from self.response_lock.acquire()
                release = True
                response = SocketIOResponse(match_response)
                self.logger.info('get response %s', response)
                self.response.append(response)

            yield from self.websocket.send(data)

            if match_response is not None:
                self.response_lock.release()
                release = False

                if response_timeout is not None:
                    res = asyncio.wait_for(response.future,
                                           response_timeout,
                                           loop=self.loop)
                else:
                    res = response.future

                try:
                    res = yield from res
                    self.logger.info('%s', res)
                except asyncio.CancelledError:
                    self.logger.info('response cancelled %s', event)
                    raise
                except asyncio.TimeoutError as ex:
                    self.logger.info('response timeout %s', event)
                    response.cancel()
                    res = None
                finally:
                    yield from self.response_lock.acquire()
                    try:
                        self.response.remove(response)
                    except ValueError:
                        pass
                    finally:
                        self.response_lock.release()

                self.logger.info('response %s %r', event, res)
                return res
        except asyncio.CancelledError:
            self.logger.error('emit cancelled')
            raise
        except Exception as ex:
            self.logger.error('emit error: %r', ex)
            if not isinstance(ex, SocketIOError):
                ex = SocketIOError(ex)
            raise ex
        finally:
            if release:
                self.response_lock.release()

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
                elif data.startswith('4'):
                    try:
                        if data[1] == '0':
                            event = ''
                            data = None
                        elif data[1] == '1':
                            event = data[2:]
                            data = None
                        else:
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
                        yield from self.events.put((event, data))
                        for response in self.response:
                            if response.match(event, data):
                                self.logger.debug('response %s %s', event, data)
                                response.set((event, data))
                                break
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
        `asyncio.CancelledError`
        """
        loop = loop or asyncio.get_event_loop()
        i = 0
        while True:
            try:
                io = yield from cls._connect(url, qsize, loop, get, connect)
                return io
            except asyncio.CancelledError:
                cls.logger.error(
                    'connect(%s) (try %d / %d): cancelled',
                    url, i + 1, retry + 1
                )
                raise
            except Exception as ex:
                cls.logger.error(
                    'connect(%s) (try %d / %d): %r',
                    url, i + 1, retry + 1, ex
                )
                if i == retry:
                    raise ConnectionFailed(ex)
            i += 1
            yield from asyncio.sleep(retry_delay)
