#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2022      David Straub
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

"""Object storage (e.g. S3) handling utilities."""

from typing import BinaryIO, List, Optional

import boto3
from botocore.exceptions import ClientError
from flask import current_app, redirect, send_file
from gramps.gen.lib import Media

from .file import FileHandler
from .image import ThumbnailHandler
from ..const import MIME_JPEG

from gramps_webapi.util import get_extension


def get_client(endpoint_url: Optional[str] = None):
    """Return an S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        config=boto3.session.Config(
            s3={"addressing_style": "path"}, signature_version="s3v4"
        ),
    )


class ObjectStorageFileHandler(FileHandler):
    """Handler for files on object storage (e.g. S3)."""

    URL_LIFETIME = 3600

    def __init__(self, handle, bucket_name: str, endpoint_url: Optional[str] = None):
        """Initialize self given a handle and media base directory."""
        super().__init__(handle)
        self.client = get_client(endpoint_url)
        self.bucket_name = bucket_name
        self.object_name = self.checksum

    def _get_presigned_url(self, expires_in: float):
        """Get a presigned URL to a file object."""
        try:
            response = self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": self.object_name,
                    "ResponseContentType": self.mime,
                },
                ExpiresIn=expires_in,
            )
        except ClientError as err:
            current_app.logger.error(err)
            return None
        return response

    def _download_fileobj(self) -> BinaryIO:
        current_app.logger.error(f"s3://{self.bucket_name}/{self.object_name}")
        response = self.client.get_object(Bucket=self.bucket_name, Key=self.object_name)
        return response["Body"]

    def file_exists(self) -> bool:
        """Check if the file exists."""
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=self.object_name)
            return True
        except ClientError:
            return False

    def send_file(self, etag: Optional[str] = None):
        """Send media file to client."""
        url = self._get_presigned_url(expires_in=self.URL_LIFETIME)
        return redirect(url, 307)

    def send_cropped(self, x1: int, y1: int, x2: int, y2: int, square: bool = False):
        """Send cropped image."""
        fileobj = self._download_fileobj()
        thumb = ThumbnailHandler(fileobj, self.mime)
        buffer = thumb.get_cropped(x1=x1, y1=y1, x2=x2, y2=y2, square=square)
        return send_file(buffer, mimetype=MIME_JPEG)

    def send_thumbnail(self, size: int, square: bool = False):
        """Send thumbnail of image."""
        fileobj = self._download_fileobj()
        thumb = ThumbnailHandler(fileobj, self.mime)
        buffer = thumb.get_thumbnail(size=size, square=square)
        return send_file(buffer, mimetype=MIME_JPEG)

    def send_thumbnail_cropped(
        self, size: int, x1: int, y1: int, x2: int, y2: int, square: bool = False
    ):
        """Send thumbnail of cropped image."""
        fileobj = self._download_fileobj()
        thumb = ThumbnailHandler(fileobj, self.mime)
        buffer = thumb.get_thumbnail_cropped(
            size=size, x1=x1, y1=y1, x2=x2, y2=y2, square=square
        )
        return send_file(buffer, mimetype=MIME_JPEG)


def upload_file_s3(
    bucket_name: str,
    stream: BinaryIO,
    checksum: str,
    mime: str,
    endpoint_url: Optional[str] = None,
) -> None:
    """Upload a file from a stream, returning the file path."""
    if not mime:
        raise ValueError("Missing MIME type")
    client = get_client(endpoint_url)
    client.upload_fileobj(
        stream, bucket_name, checksum, ExtraArgs={"ContentType": mime}
    )


def filter_existing_files_s3(
    bucket_name: str,
    objects: List[Media],
    endpoint_url: Optional[str] = None,
) -> List[Media]:
    """Given a list of media objects, return the ones with existing files."""
    client = get_client(endpoint_url)
    contents = client.list_objects(Bucket=bucket_name)["Contents"]
    bucket_checksums = set(obj["Key"] for obj in contents)
    return [obj for obj in objects if obj.checksum in bucket_checksums]
