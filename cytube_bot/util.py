import asyncio
import logging
from hashlib import md5
from base64 import b64encode
from itertools import islice
from collections import Sequence

import requests


logger = logging.getLogger(__name__)


if hasattr(asyncio.Queue, 'task_done'):
    Queue = asyncio.Queue
else:
    class Queue(asyncio.Queue):
        def task_done(self):
            logger.debug('task_done %s', self)

        @asyncio.coroutine
        def join(self):
            logger.info('join %s', self)


def to_sequence(obj):
    if obj is None:
        return ()
    if isinstance(obj, str) or not isinstance(obj, Sequence):
        return (obj,)
    return obj


def get(url, loop):
    """Asynchronous HTTP GET request.

    Parameters
    ----------
    url: `str`
    loop: `asyncio.events.AbstractEventLoop`

    Returns
    -------
    `asyncio.futures.Future`
    """
    return loop.run_in_executor(None, lambda: requests.get(url).text)


def ip_hash(string, length):
    res = md5(string.encode('utf-8')).digest()
    return b64encode(res)[:length].decode('utf-8')


def cloak_ip(ip, start=0):
    parts = ip.split('.')
    acc = ''
    for i, part in islice(enumerate(parts), start, None):
        parts[i] = ip_hash('%s%s%s' % (acc, part, i), 3)
        acc += part
    while len(parts) < 4:
        parts.append('*')
    return '.'.join(parts)


def _uncloak_ip(cloaked_parts, uncloaked_parts, acc, i, ret):
    if i > 3:
        ret.append('.'.join(uncloaked_parts))
        return
    for part in range(256):
        part_hash = ip_hash('%s%s%s' % (acc, part, i), 3)
        if part_hash == cloaked_parts[i]:
            uncloaked_parts[i] = str(part)
            _uncloak_ip(
                cloaked_parts,
                uncloaked_parts,
                '%s%d' % (acc, part),
                i + 1,
                ret
            )

def uncloak_ip(ip, start=0):
    parts = ip.split('.')
    if start is None:
        for start, part in enumerate(parts):
            try:
                val = int(part)
                if val < 0 or val > 255:
                    break
            except ValueError:
                break
    ret = []
    _uncloak_ip(parts, list(parts), '', start, ret)
    return ret
