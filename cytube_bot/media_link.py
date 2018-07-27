import os
import re
import logging
from urllib.parse import urlparse, parse_qsl


class MediaLink:
    """Media link.

    Attributes
    ----------
    type : `str`
        Link type.
    id : `str`
        Link ID.
    FILE_TYPES : `list` of `str`
        Supported raw file extensions.
    URL_TO_LINK : `list` of (`str`, `str`, `str`)
        (url regexp, type format string, id format string)
    LINK_TO_URL : `dict` of (`str`, `str`)
        (type, url format string)
    """

    logger = logging.getLogger(__name__)

    URL_TO_LINK = [
        (r'youtube\.com/watch\?([^#]+)', 'yt', '{v}'),
        (r'youtu\.be/([^\?&#]+)', 'yt', '{0}'),
        (r'youtube\.com/playlist\?([^#]+)', 'yp', '{list}'),
        (r'clips\.twitch\.tv/([A-Za-z]+)', 'tc', '{0}'),
        (r'twitch\.tv/(?:.*?)/([cv])/(\d+)', 'tv', '{0}{1}'),
        (r'twitch\.tv/videos/(\d+)', 'tv', 'v{0}'),
        (r'twitch\.tv/([\w-]+)', 'tw', '{0}'),
        (r'livestream\.com/([^\?&#]+)', 'li', '{0}'),
        (r'ustream\.tv/([^\?&#]+)', 'us', '{0}'),
        (r'(?:hitbox|smashcast)\.tv/([^\?&#]+)', 'hb', '{0}'),
        (r'vimeo\.com/([^\?&#]+)', 'vi', '{0}'),
        (r'dailymotion\.com/video/([^\?&#_]+)', 'dm', '{0}'),
        (r'imgur\.com/a/([^\?&#]+)', 'im', '{0}'),
        (r'soundcloud\.com/([^\?&#]+)', 'sc', '{url}'),
        (r'(?:docs|drive)\.google\.com/file/d/([a-zA-Z0-9_-]+)', 'gd', '{0}'),
        (r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)', 'gd', '{0}'),
        (r'vid\.me/embedded/([\w-]+)', 'vm', '{0}'),
        (r'vid\.me/([\w-]+)', 'vm', '{0}'),
        (r'(.*\.m3u8)', 'hl', '{url}'),
        (r'streamable\.com/([\w-]+)', 'sb', '{0}'),
        (r'^dm:([^\?&#_]+)', 'dm', '{0}'),
        (r'^fi:(.*)', 'fi', '{0}'),
        (r'^cm:(.*)', 'cm', '{0}'),
        (r'^([a-z]{2}):([^\?&#]+)', '{0}', '{1}')
    ]

    FILE_TYPES = [
        '.mp4', '.flv', '.webm', '.ogg',
        '.ogv', '.mp3', '.mov', '.m4a'
    ]

    LINK_TO_URL = {
        'yt': 'https://youtube.com/watch?v={0}',
        'yp': 'https://youtube.com/playlist?list={0}',
        'tc': 'https://clips.twitch.tv/{0}',
        #'tv': 'https://twitch.tv/videos/{0}',
        'tw': 'https://twitch.tv/{0}',
        'li': 'https://livestream.com/{0}',
        'us': 'https://www.ustream.tv/{0}',
        'hb': 'https://smashcast.tv/{0}',
        'vi': 'https://vimeo.com/{0}',
        'dm': 'https://dailymotion.com/video/{0}',
        'im': 'https://imgur.com/a/{0}',
        'sc': 'https://soundcloud.com/{0}',
        'gd': 'https://drive.google.com/file/d/{0}',
        'vm': 'https://vid.me/{0}',
        'hl': '{0}',
        'sb': 'https://streamable.com/{0}',
        'fi': '{0}',
        'cm': '{0}',
        'rt': '{0}'
    }

    def __init__(self, type_, id_):
        self.type = type_
        self.id = id_

    def __str__(self):
        return '%s:%s' % (self.type, self.id)

    def __repr__(self):
        return 'MediaLink(%r, %r)' % (self.type, self.id)

    def __eq__(self, link):
        return (
            isinstance(link, self.__class__)
            and self.type == link.type
            and self.id == link.id
        )

    @property
    def url(self):
        """Media URL.
        """
        try:
            url = self.LINK_TO_URL[self.type]
        except KeyError:
            self.logger.warning(
                'unknown media type "%s" (id="%s")',
                self.type, self.id
            )
            return '{0}:{1}'.format(self.type, self.id)
        return url.format(self.id)

    @classmethod
    def from_url(cls, url):
        """Create a media link from URL.

        Parameters
        ----------
        url : `str`
            Media URL.

        Returns
        -------
        MediaLink

        Raises
        ------
        ValueError
            If media URL is not supported.
        """
        url = url.strip().replace('feature=player_embedded&', '')
        parsed_url = urlparse(url)

        if parsed_url.scheme == 'rtmp':
            return cls('rt', url)

        for expr, type_, id_ in cls.URL_TO_LINK:
            match = re.search(expr, url)
            if match is not None:
                args = match.groups()
                kwargs = dict(parse_qsl(parsed_url.query))
                kwargs['url'] = url
                return cls(
                    type_.format(*args, **kwargs),
                    id_.format(*args, **kwargs)
                )

        if parsed_url.scheme == 'https':
            _, ext = os.path.splitext(parsed_url.path)
            if ext == '.json':
                return cls('cm', url)
            if ext in cls.FILE_TYPES:
                return cls('fi', url)
            raise ValueError(
                'The file you are attempting to queue does not match the'
                ' supported file extensions %s.'
                ' For more information about why other filetypes'
                ' are not supported, see https://git.io/va9g9'
                % ', '.join(cls.FILE_TYPES)
            )

        raise ValueError('Raw files must begin with "https".'
                         ' Plain http is not supported.')
