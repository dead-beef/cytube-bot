import sys
import socket
import logging

try:
    import socks
    HAS_PYSOCKS = True
    SOCKS5 = socks.SOCKS5
    ProxyError = socks.ProxyError
except ImportError:
    HAS_PYSOCKS = False
    SOCKS5 = None
    class ProxyError(Exception):
        pass

from .error import ProxyConfigError


logger = logging.getLogger('socks.getaddrinfo')
_orig_getaddrinfo = socket.getaddrinfo


# https://web.archive.org/web/20161211104525/http://fitblip.pub/2012/11/13/proxying-dns-with-python/
def getaddrinfo(host, port, *args, **kwargs):
    proxy_type, _, _, rdns, _, _ = socks.get_default_proxy()
    if proxy_type is not None and rdns:
        ret = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (host, port))]
    else:
        ret = _orig_getaddrinfo(host, port, *args, **kwargs)
    logger.debug('%s:%s %s', host, port, ret)
    return ret


def wrap_module(module):
    logger.debug('wrap module %s', module)
    socks.wrap_module(module)
    module.socket.getaddrinfo = getaddrinfo


def set_proxy(addr, port, proxy_type=SOCKS5, modules=None):
    """Set SOCKS proxy for all connections.

    Parameters
    ----------
    addr : `str`
        Proxy IP.
    port : `int`
        Proxy port.
    proxy_type : `int`, optional
        `socks.SOCKS4` or `socks.SOCKS5`.
    modules : `None` or `list` of `types.ModuleType`, optional
        Modules to wrap (default: (sys.modules[__name__],)).

    Raises
    ------
    cytube_bot.error.ProxyConfigError
        If pysocks is not installed.
    """
    if not HAS_PYSOCKS:
        raise ProxyConfigError('pysocks is not installed')
    socks.set_default_proxy(
        proxy_type=proxy_type,
        addr=addr,
        port=port,
        rdns=proxy_type == socks.SOCKS5
    )
    for module in modules or (sys.modules[__name__],):
        wrap_module(module)
