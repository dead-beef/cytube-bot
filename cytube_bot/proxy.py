import sys
import socket
import logging

try:
    import socks
    HAS_PYSOCKS = True
    SOCKS5 = socks.SOCKS5

    ProxyError = socks.ProxyError
    socksocket = socks.socksocket
except ImportError:
    HAS_PYSOCKS = False
    SOCKS5 = None

    class ProxyError(Exception):
        pass

    class socksocket: # pylint: disable=invalid-name,too-few-public-methods
        def __init__(self, *args, **kwargs):
            raise ProxyConfigError('pysocks is not installed')


from .error import ProxyConfigError


logger = logging.getLogger('socks.getaddrinfo')
_orig_getaddrinfo = socket.getaddrinfo


class Socket(socksocket):
    """SOCKS enabled socket (no proxy for localhost)."""

    def __init__(self,
                 family=socket.AddressFamily.AF_INET,
                 type=socket.SocketType.SOCK_STREAM,
                 proto=0,
                 fileno=None):
        if type not in (socket.SocketType.SOCK_STREAM,
                        socket.SocketType.SOCK_DGRAM):
            type = socket.SocketType.SOCK_STREAM
        super().__init__(family, type, proto, fileno)

    def set_proxy_for_address(self, addr):
        """Unset proxy for localhost.

        Parameters
        ----------
        host : `str`
        """
        logger.debug('set_proxy_for_address %r', addr)
        host, _ = addr
        if host in ('127.0.0.1', 'localhost'):
            self.set_proxy(None)
        else:
            self.proxy = self.default_proxy

    def bind(self, addr, *args, **kwargs):
        self.set_proxy_for_address(addr)
        return super().bind(addr, *args, **kwargs)

    def sendto(self, data, *args, **kwargs):
        self.set_proxy_for_address(args[-1])
        return super().sendto(data, *args, **kwargs)

    def connect(self, addr, *args, **kwargs):
        self.set_proxy_for_address(addr)
        return super().connect(addr, *args, **kwargs)


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

    if not HAS_PYSOCKS:
        raise ProxyConfigError('pysocks is not installed')

    if socksocket.default_proxy:
        module.socket.socket = Socket
        module.socket.getaddrinfo = getaddrinfo
    else:
        raise ProxyConfigError('no default proxy specified')


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
