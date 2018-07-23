class CytubeError(Exception):
    pass

class ProxyConfigError(CytubeError):
    pass

class SocketConfigError(CytubeError):
    pass

class LoginError(CytubeError):
    pass

class Kicked(CytubeError):
    pass

class ChannelError(CytubeError):
    pass

class ChannelPermissionError(ChannelError):
    pass

class SocketIOError(Exception):
    pass

class ConnectionFailed(SocketIOError):
    pass

class ConnectionClosed(SocketIOError):
    pass

class PingTimeout(ConnectionClosed):
    pass
