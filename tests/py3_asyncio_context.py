import asyncio
import sys

import pytest

from talisker.util import pkg_is_installed
from talisker import Context
from talisker import context


def test_context_asyncio():
    if sys.version_info < (3, 7):
        if sys.version_info < (3, 5, 3):
            pytest.skip(
                'aiocontextvars does not work in python {}'.format(
                    sys.version
                )
            )
        elif not pkg_is_installed('aiocontextvars'):
            pytest.skip('aiocontextvars not installed')

    async def r1():
        Context.new()
        Context.logging.push(a=1)
        Context.track('test', 1.0)
        assert Context.logging.flat == {'a': 1}
        assert Context.current().tracking['test'].count == 1

        await sub()

        # changes made by sub should be visible
        assert Context.logging.flat == {'a': 2}
        assert Context.current().tracking['test'].count == 2

    async def sub():
        # should be same context as r1
        assert Context.logging.flat == {'a': 1}
        Context.logging.push(a=2)
        Context.track('test', 1.0)
        assert Context.logging.flat == {'a': 2}
        assert Context.current().tracking['test'].count == 2

    async def r2():
        # should be a separate context from r1
        Context.new()
        Context.logging.push(a=3)
        Context.track('test', 1.0)
        assert Context.logging.flat == {'a': 3}
        assert Context.current().tracking['test'].count == 1

    # ensure we have no context
    loop = asyncio.get_event_loop()
    Context.clear()
    t1 = loop.create_task(r1())
    t2 = loop.create_task(r2())
    loop.run_until_complete(asyncio.gather(t1, t2))
