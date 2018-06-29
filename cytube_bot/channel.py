import logging

from .playlist import Playlist
from .error import ChannelPermissionError


class Channel:
    """CyTube channel.

    Attributes
    ----------
    name : `str`
    password : `str` or None
    drink_count : `int`
    user_count: `int`
    motd: `str`
    css: `str`
    js: `str`
    emotes: `list` of `dict`
    permissions : `dict` of (`str`, `int`)
    options : `dict`
    users : `list` of `cytube_bot.user.User`
    playlist : `list` of `cytube_bot.playlist.PlaylistItem`
    """

    logger = logging.getLogger(__name__)

    def __init__(self, name, password=None):
        self.name = name
        self.password = password
        self.drink_count = 0
        self.user_count = 0
        self.motd = ''
        self.css = ''
        self.js = ''
        self.emotes = []
        self.permissions = {}
        self.options = {}
        self.users = []
        self.playlist = Playlist()

    def __str__(self):
        return '<channel "%s">' % self.name

    __repr__ = __str__

    def add_user(self, user):
        if user in self.users:
            self.logger.warning('add_user: user exists: %s', user)
        else:
            self.users.append(user)

    def remove_user(self, user):
        try:
            self.users.remove(user)
        except ValueError:
            self.logger.warning('remove_user: user not found: %s', user)

    def update_user(self, user, **kwargs):
        try:
            user = self.users[self.users.index(user)]
        except ValueError:
            self.logger.warning('update_user: user not found: %s', user)
        else:
            self.logger.info('update_user %s', user)
            user.update(**kwargs)

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
