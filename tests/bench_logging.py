import sys
import logging


def talisker():
    from talisker import logs
    logs.configure()
    logger = logging.getLogger(__name__)
    logs.logging_context.push(a=1, b=2, c=3)
    return logger


def stdlib():
    format = '%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s "%(message)s"'
    logger = logging.getLogger(__name__)
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(format))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return logger


type = sys.argv[1]
if len(sys.argv) > 2:
    n = int(sys.argv[2])
else:
    n = 100000

if type == 'talisker':
    logger = talisker()
else:
    logger = stdlib()

d = {'foo': 'bar'}
for i in range(n):
    logger.info('test', extra=d)
