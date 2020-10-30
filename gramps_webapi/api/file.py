"""File handling utilities."""

import os

from flask import send_from_directory
from gramps.gen.lib import Media

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
