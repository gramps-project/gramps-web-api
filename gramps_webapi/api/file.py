#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""File handling utilities."""

import hashlib
import os
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Optional, Tuple, Union

from flask import abort, make_response, send_file, send_from_directory
from gramps.gen.errors import HandleError
from gramps.gen.lib import Media
from werkzeug.datastructures import FileStorage

from gramps_webapi.const import MIME_JPEG

from ..types import FilenameOrPath
from .image import LocalFileThumbnailHandler
from .util import get_db_handle, get_media_base_dir


class FileHandler:
    """Generic handler for a single media file."""

    def __init__(self, handle):
        """Initialize self."""
        self.handle = handle
        self.media = self._get_media_object()
        self.mime = self.media.mime
        self.path = self.media.path
        self.checksum = self.media.checksum

    def _get_media_object(self) -> Optional[Media]:
        """Get the media object from the database."""
        db_handle = get_db_handle()
        try:
            return db_handle.get_media_from_handle(self.handle)
        except HandleError:
            return None

    def file_exists(self) -> bool:
        """Check if the file exists."""
        raise NotImplementedError

    def send_file(self, etag=Optional[str]):
        """Send media file to client."""
        raise NotImplementedError

    def send_cropped(self, x1: int, y1: int, x2: int, y2: int, square: bool = False):
        """Send cropped media file to client."""
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
            raise ValueError(f"Directory {self.base_dir} does not exist")
        if os.path.isabs(self.path):
            self.path_abs = self.path
            self.path_rel = os.path.relpath(self.path, self.base_dir)
        else:
            self.path_abs = os.path.join(self.base_dir, self.path)
            self.path_rel = self.path

    def _check_path(self) -> None:
        """Check whether the file path is contained within the base dir.

        If not, a `ValueError` is raised.
        """
        base_dir = Path(self.base_dir).resolve()
        file_path = Path(self.path_abs).resolve()
        if base_dir not in file_path.parents:
            raise ValueError(f"File {file_path} is not within the base directory.")

    def file_exists(self) -> bool:
        """Check if the file exists."""
        self._check_path()
        return Path(self.path_abs).is_file()

    def send_file(self, etag: Optional[str] = None):
        """Send media file to client."""
        res = make_response(
            send_from_directory(self.base_dir, self.path_rel, mimetype=self.mime)
        )
        if etag:
            res.headers["ETag"] = etag
        return res

    def send_cropped(self, x1: int, y1: int, x2: int, y2: int, square: bool = False):
        """Send cropped image."""
        try:
            self._check_path()
        except ValueError:
            abort(403)
        thumb = LocalFileThumbnailHandler(self.path_abs, self.mime)
        buffer = thumb.get_cropped(x1=x1, y1=y1, x2=x2, y2=y2, square=square)
        return send_file(buffer, mimetype=MIME_JPEG)

    def send_thumbnail(self, size: int, square: bool = False):
        """Send thumbnail of image."""
        try:
            self._check_path()
        except ValueError:
            abort(403)
        thumb = LocalFileThumbnailHandler(self.path_abs, self.mime)
        buffer = thumb.get_thumbnail(size=size, square=square)
        return send_file(buffer, mimetype=MIME_JPEG)

    def send_thumbnail_cropped(
        self, size: int, x1: int, y1: int, x2: int, y2: int, square: bool = False
    ):
        """Send thumbnail of cropped image."""
        try:
            self._check_path()
        except ValueError:
            abort(403)
        thumb = LocalFileThumbnailHandler(self.path_abs, self.mime)
        buffer = thumb.get_thumbnail_cropped(
            size=size, x1=x1, y1=y1, x2=x2, y2=y2, square=square
        )
        return send_file(buffer, mimetype=MIME_JPEG)


def upload_file_local(
    base_dir: FilenameOrPath, rel_path: FilenameOrPath, stream: BinaryIO
) -> None:
    """Upload a file from a stream, returning the file path."""
    fs = FileStorage(stream)
    fs.save(os.path.join(base_dir, rel_path))


def get_checksum(fp) -> str:
    """Get the checksum of a file-like object."""
    md5 = hashlib.md5()
    try:
        while True:
            buf = fp.read(65536)
            if not buf:
                break
            md5.update(buf)
        md5sum = md5.hexdigest()
    except (IOError, UnicodeEncodeError):
        return ""
    return md5sum


def process_file(stream: Union[Any, BinaryIO]) -> Tuple[str, BinaryIO]:
    """Process a file from a stream that has a read method."""
    fp = BytesIO()
    fp.write(stream.read())
    fp.seek(0)
    checksum = get_checksum(fp)
    if not checksum:
        raise IOError("Unable to process file.")
    fp.seek(0)
    return checksum, fp
