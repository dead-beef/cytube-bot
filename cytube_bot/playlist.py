from .media_link import MediaLink


class PlaylistItem:
    """CyTube playlist item.

    Attributes
    ----------
    link : `cytube_bot.media_link.MediaLink`
        Media link.
    uid : `int`
        Playlist item ID.
    temp : `bool`
        `True` if item is temporary.
    duration : `int`
        Duration in seconds.
    title : `str`
    username : `str`
    """

    def __init__(self, data):
        self.uid = data['uid']
        self.temp = data['temp']
        self.username = data['queueby']
        data = data['media']
        self.link = MediaLink(data['type'], data['id'])
        self.title = data['title']
        self.duration = data['seconds']

    def __str__(self):
        return '<playlist item #%s "%s">' % (self.uid, self.title)

    __repr__ = __str__

    def __eq__(self, item):
        if not isinstance(item, PlaylistItem):
            return self.uid == item
        return self.uid == item.uid


class Playlist:
    """CyTube playlist.

    Attributes
    ----------
    time : `int`
        Playlist duration in seconds.
    current : `None` or `cytube_bot.playlist.PlaylistItem`
        Current playlist item.
    current_time : `int`
        Current playlist item time in seconds.
    locked : `bool`
        `True` if playlist is locked.
    paused : `bool`
        `True` if playlist is paused.
    queue : `list` of `cytube_bot.playlist.PlaylistItem`
    """

    def __init__(self):
        self.time = 0
        self.locked = False
        self.paused = True
        self.current_time = 0
        self._current = None
        self.queue = []

    def __str__(self):
        return '<playlist %s>' % self.queue

    __repr__ = __str__

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, current):
        if current is not None and not isinstance(current, PlaylistItem):
            current = self.get(current)
        self._current = current

    def index(self, item):
        """Get playlist item index by ID.

        Parameters
        ----------
        item : `int`
            Playlist item ID.

        Returns
        -------
        `int`

        Raises
        ------
        ValueError
            If item does not exist.
        """
        return self.queue.index(item)

    def get(self, uid):
        """Get playlist item by ID.

        Parameters
        ----------
        item : `int`
            Playlist item ID.

        Returns
        -------
        `cytube_bot.playlist.PlaylistItem`

        Raises
        ------
        ValueError
            If item does not exist.
        """
        return self.queue[self.index(uid)]

    def remove(self, item):
        """Remove playlist item.

        Parameters
        ----------
        item : `int` or `cytube_bot.playlist.PlaylistItem`
            Playlist item or ID.

        Raises
        ------
        ValueError
            If item does not exist.
        """
        if self.current == item:
            self.current = None
            self.current_time = 0
            self.paused = True
        self.queue.remove(item)

    def add(self, after, item):
        """Add playlist item.

        Parameters
        ----------
        after : `int` or `None`
            `int` - insert after item with ID, `None` - append.
        item : `dict` or `cytube_bot.playlist.PlaylistItem`
            Playlist item or data.
        """
        if not isinstance(item, PlaylistItem):
            item = PlaylistItem(item)
        if not isinstance(after, int):
            self.queue.append(item)
        else:
            self.queue.insert(self.index(after) + 1, item)

    def move(self, item, after):
        """Move playlist item.

        Parameters
        ----------
        after : `int`
        item : `int`
        """
        item = self.get(item)
        self.remove(item)
        self.add(after, item)

    def clear(self):
        """Clear playlist.
        """
        self.time = 0
        self.paused = True
        self.current = None
        self.current_time = 0
        self.queue.clear()
