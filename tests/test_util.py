import asyncio
import pytest

from cytube_bot.util import Queue, to_sequence, cloak_ip, uncloak_ip


@pytest.mark.asyncio
@asyncio.coroutine
def test_queue(event_loop):
    queue = Queue(loop=event_loop)
    assert isinstance(queue, asyncio.Queue)
    yield from queue.put(0)
    res = yield from queue.get()
    assert res == 0
    queue.task_done()
    yield from queue.join()


@pytest.mark.parametrize('test,res', [
    (None, ()),
    (0, (0,)),
    ('str', ('str',)),
    ({'x': 0}, ({'x': 0},)),
    ((0, 1), None),
    ([0, 1], None)
])
def test_to_sequence(test, res):
    if res is None:
        assert to_sequence(test) is test
    else:
        assert to_sequence(test) == res


@pytest.mark.parametrize('test,res', [
    (('127.0.0.1',), 'yFA.j8g.iXh.gvS'),
    (('127.0.0.1', 2), '127.0.ou9.RBl')
])
def test_cloak_ip(test, res):
    assert cloak_ip(*test) == res


@pytest.mark.parametrize('test,res', [
    (('yFA.j8g.iXh.gvS',), ['127.0.0.1']),
    (('127.0.ou9.RBl',), []),
    (('127.0.ou9.RBl', 2), ['127.0.0.1']),
    (('127.0.ou9.RBl', None), ['127.0.0.1'])
])
def test_uncloak_ip(test, res):
    assert uncloak_ip(*test) == res
