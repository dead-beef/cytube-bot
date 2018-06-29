class PlaylistItem:
    def __init__(self, data):
        self.uid = data['uid']
        self.temp = data['temp']
        self.username = data['queueby']
        data = data['media']
        self.title = data['title']
        self.type = data['type']
        self.duration = data['seconds']
        self.id = data['id']

    def __str__(self):
        return '<playlist item #%s "%s">' % (self.uid, self.title)

    __repr__ = __str__

    def __eq__(self, item):
        if not isinstance(item, PlaylistItem):
            return self.uid == item
        return self.uid == item.uid


class Playlist:
    def __init__(self):
        self.time = 0
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
        return self.queue.index(item)

    def get(self, uid):
        return self.queue[self.index(uid)]

    def remove(self, item):
        if self.current == item:
            self.current = None
            self.current_time = 0
            self.paused = True
        self.queue.remove(item)

    def add(self, after, data):
        item = PlaylistItem(data)
        if not isinstance(after, int):
            self.queue.append(item)
        else:
            self.queue.insert(self.index(after) + 1, item)

    def clear(self):
        self.time = 0
        self.paused = True
        self.current = None
        self.current_time = 0
        self.queue.clear()
