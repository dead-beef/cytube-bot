class CytubeError(Exception):
    pass

class SocketConfigError(CytubeError):
    pass

class ChannelError(CytubeError):
    pass

class ChannelPermissionError(CytubeError):
    pass

class Kicked(CytubeError):
    pass

class LoginError(CytubeError):
    pass

class SocketIOError(Exception):
    pass

class ConnectionFailed(SocketIOError):
    pass

class ConnectionClosed(SocketIOError):
    pass
