import asyncio
import pytest

from cytube_bot.util import Queue


@pytest.mark.asyncio
@asyncio.coroutine
def test_queue(event_loop):
    q = Queue(loop=event_loop)
    assert isinstance(q, asyncio.Queue)
    yield from q.put(0)
    res = yield from q.get()
    assert res == 0
    q.task_done()
    yield from q.join()
