import logging

from .playlist import Playlist
from .user import UserList
from .error import ChannelPermissionError


class Channel:
    """CyTube channel.

    Attributes
    ----------
    name : `str`
    password : `str` or None
    drink_count : `int`
    motd: `str`
    css: `str`
    js: `str`
    emotes: `list` of `dict`
    permissions : `dict` of (`str`, `int`)
    options : `dict`
    userlist : `cytube_bot.user.UserList`
    playlist : `cytube_bot.playlist.Playlist`
    """

    logger = logging.getLogger(__name__)

    def __init__(self, name, password=None):
        self.name = name
        self.password = password
        self.drink_count = 0
        self.motd = ''
        self.css = ''
        self.js = ''
        self.emotes = []
        self.permissions = {}
        self.options = {}
        self.userlist = UserList()
        self.playlist = Playlist()

    def __str__(self):
        return '<channel "%s">' % self.name

    __repr__ = __str__

    def check_permission(self, action, user, throw=True):
        try:
            min_rank = self.permissions[action]
            if user.rank < min_rank:
                if throw:
                    raise ChannelPermissionError(
                        '"%s": permission denied (%s rank %d < %d)'
                        % (action, user.name, user.rank, min_rank)
                    )
                return False
            return True
        except KeyError:
            raise ValueError('unknown action "%s"' % action)

    def has_permission(self, action, user):
        return self.check_permission(action, user, False)
