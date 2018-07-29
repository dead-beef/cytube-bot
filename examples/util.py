import sys
import json
import logging
from html.parser import unescape, HTMLParser

from cytube_bot import SocketIO, set_proxy


class MessageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.message = ''

    def handle_starttag(self, _, attr):
        for name, value in attr:
            if name in ('src', 'href'):
                self.message += ' %s ' % value

    def handle_data(self, data):
        self.message += unescape(data)

    def parse(self, msg):
        self.message = ''
        self.feed(msg)
        self.close()
        self.reset()
        return self.message


def configure_logger(logger,
                     log_file=None,
                     log_format=None,
                     log_level=logging.INFO):
    if isinstance(log_file, str):
        handler = logging.FileHandler(log_file, 'a')
    else:
        handler = logging.StreamHandler(log_file)

    formatter = logging.Formatter(log_format)

    if isinstance(logger, str):
        logger = logging.getLogger(logger)

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(log_level)

    return logger


def configure_proxy(conf):
    proxy = conf.get('proxy', None)
    if not proxy:
        return
    proxy = proxy.rsplit(':', 1)
    if len(proxy) == 1:
        addr, port = proxy[0], 1080
    else:
        addr, port = proxy[0], int(proxy[1])
    set_proxy(addr, port)


def get_config():
    if len(sys.argv) != 2:
        print('usage: %s <config file>' % sys.argv[0], file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], 'r') as fp:
        conf = json.load(fp)

    retry = conf.get('retry', 0)
    retry_delay = conf.get('retry_delay', 1)
    log_level = getattr(logging, conf.get('log_level', 'info').upper())

    logging.basicConfig(
        level=log_level,
        format='[%(asctime).19s] [%(name)s] [%(levelname)s] %(message)s'
    )

    configure_proxy(conf)

    return conf, {
        'domain': conf['domain'],
        'user': conf.get('user', None),
        'channel': conf.get('channel', None),
        'response_timeout': conf.get('response_timeout', 0.1),
        'restart_delay': conf.get('restart_delay', None),
        'socket_io': lambda url, loop: SocketIO.connect(
            url,
            retry=retry,
            retry_delay=retry_delay,
            loop=loop
        )
    }
