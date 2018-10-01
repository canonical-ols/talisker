import logging
import statistics
from timeit import default_timer

import talisker.logs


std_formatter = logging.Formatter(
    '%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s "%(message)s"',
    '%Y-%m-%d %H:%M:%S'
)
std_handler = logging.StreamHandler()
std_handler.setFormatter(std_formatter)
std_handler.setLevel(logging.INFO)
std_logger = logging.Logger('stdlib')
std_logger.addHandler(std_handler)


talisker_formatter = talisker.logs.StructuredFormatter()
talisker_handler = logging.StreamHandler()
talisker_handler.setFormatter(talisker_formatter)
talisker_logger = talisker.logs.StructuredLogger('talisker')
talisker_logger.addHandler(talisker_handler)


def run(logger, handler, formatter):
    total_times = []
    handler_times = []
    emit_times = []
    formatter_times = []
    make_times = []

    def wrap(f, collector):
        def decorator(*args, **kwargs):
            t = default_timer()
            r = f(*args, **kwargs)
            collector.append(default_timer() - t)
            return r
        return decorator

    handler.handle = wrap(handler.handle, handler_times)
    handler.emit = wrap(handler.emit, emit_times)
    formatter.format = wrap(formatter.format, formatter_times)
    logger.makeRecord = wrap(logger.makeRecord, make_times)

    extra = {'foo': 'bar', 'baz': 12}
    for i in range(100000):
        msg = str(i)
        t = default_timer()
        logger.info(msg, extra=extra)
        total_times.append(default_timer() - t)

    total = statistics.mean(total_times) * 1000000
    handle = statistics.mean(handler_times) * 1000000
    emit = statistics.mean(emit_times) * 1000000
    format = statistics.mean(formatter_times) * 1000000
    make = statistics.mean(make_times) * 1000000

    return total, handle, emit, format, make


def output(title, total, handle, emit, format, make):
    print(title)
    print('log:          ', total)
    print('  make:       ', make)
    print('  handle:     ', handle)
    print('    emit:     ', emit)
    print('      format: ', format)


s = run(std_logger, std_handler, std_formatter)
output('stdlib', *s)
t = run(talisker_logger, talisker_handler, talisker_formatter)
output('talisker', *t)
output('summary', *(i - j for i, j in zip(t, s)))
