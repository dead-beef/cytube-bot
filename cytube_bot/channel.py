import logging

from .playlist import Playlist
from .user import UserList
from .error import ChannelPermissionError


class Channel:
    """CyTube channel.

    Attributes
    ----------
    name : `str`
    password : `str` or `None`
    drink_count : `int`
    voteskip_count: `int`
    voteskip_need: `int`
    motd: `str`
    css: `str`
    js: `str`
    emotes: `list` of `dict`
    permissions : `dict` of (`str`, `float`)
    options : `dict`
    userlist : `cytube_bot.user.UserList`
    playlist : `cytube_bot.playlist.Playlist`
    """

    logger = logging.getLogger(__name__)

    RANK_PRECISION = 1e-4

    def __init__(self, name='', password=None):
        self.name = name
        self.password = password
        self.drink_count = 0
        self.voteskip_count = 0
        self.voteskip_need = 0
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
        """Check if user has permission.

        Parameters
        ----------
        action : `str`
            Permission to check.
        user : `cytube_bot.user.User`
            User.
        throw : `bool`, optional
            `True` to raise exception if user does not have permission.

        Returns
        -------
        `bool`
            `True` if user has permission.

        Raises
        ------
        ChannelPermissionError
            If user does not have permission.
        ValueError
            If permission does not exist.
        """
        try:
            min_rank = self.permissions[action]
            if user.rank + self.RANK_PRECISION < min_rank:
                if throw:
                    raise ChannelPermissionError(
                        '"%s": permission denied (%s rank %.2f < %.2f)'
                        % (action, user.name, user.rank, min_rank)
                    )
                return False
            return True
        except KeyError:
            raise ValueError('unknown action "%s"' % action)

    def has_permission(self, action, user):
        """check_permission(action, user, False)
        """
        return self.check_permission(action, user, False)
