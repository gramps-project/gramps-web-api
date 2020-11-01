"""File handling utilities."""

import os

from flask import send_file, send_from_directory
from gramps.gen.lib import Media

from gramps_webapi.const import MIME_JPEG

from .image import ThumbnailHandler
from .util import get_dbstate, get_media_base_dir


class FileHandler:
    """Generic media file handler."""

    def __init__(self, handle):
        """Initialize self."""
        self.handle = handle
        self.media = self._get_media_object()
        self.mime = self.media.mime
        self.path = self.media.path
        self.checksum = self.media.checksum

    def _get_media_object(self) -> Media:
        """Get the media object from the database."""
        dbstate = get_dbstate()
        return dbstate.db.get_media_from_handle(self.handle)

    def send_file(self):
        """Send media file to client."""
        raise NotImplementedError

    def send_thumbnail(self, size: int, square: bool = False):
        """Send thumbnail of image."""
        raise NotImplementedError

    def send_thumbnail_cropped(
        self, size: int, x1: int, y1: int, x2: int, y2: int, square: bool = False
    ):
        """Send thumbnail of cropped image."""
        raise NotImplementedError


class LocalFileHandler(FileHandler):
    """Handler for local files."""

    def __init__(self, handle, base_dir=None):
        """Initialize self given a handle and media base directory."""
        super().__init__(handle)
        self.base_dir = base_dir or get_media_base_dir()
        if not os.path.isdir(self.base_dir):
            raise ValueError("Directory {} does not exist".format(self.base_dir))
        if os.path.isabs(self.path):
            self.path_abs = self.path
            self.path_rel = os.path.relpath(self.path, self.base_dir)
        else:
            self.path_abs = os.path.join(self.base_dir, self.path)
            self.path_rel = self.path

    def send_file(self):
        """Send media file to client."""
        return send_from_directory(
            directory=self.base_dir, filename=self.path_rel, mimetype=self.mime
        )

    def send_cropped(self, x1: int, y1: int, x2: int, y2: int, square: bool = False):
        """Send cropped image."""
        thumb = ThumbnailHandler(self.path_abs, self.mime)
        buffer = thumb.get_cropped(x1=x1, y1=y1, x2=x2, y2=y2, square=square)
        return send_file(buffer, mimetype=MIME_JPEG)

    def send_thumbnail(self, size: int, square: bool = False):
        """Send thumbnail of image."""
        thumb = ThumbnailHandler(self.path_abs, self.mime)
        buffer = thumb.get_thumbnail(size=size, square=square)
        return send_file(buffer, mimetype=MIME_JPEG)

    def send_thumbnail_cropped(
        self, size: int, x1: int, y1: int, x2: int, y2: int, square: bool = False
    ):
        """Send thumbnail of cropped image."""
        thumb = ThumbnailHandler(self.path_abs, self.mime)
        buffer = thumb.get_thumbnail_cropped(
            size=size, x1=x1, y1=y1, x2=x2, y2=y2, square=square
        )
        return send_file(buffer, mimetype=MIME_JPEG)
