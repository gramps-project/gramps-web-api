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

from typing import BinaryIO, Dict, Optional

import boto3
from botocore.exceptions import ClientError
from flask import current_app, redirect, send_file
from gramps.gen.db.base import DbReadBase

from ..const import MIME_JPEG
from .file import FileHandler
from .image import ThumbnailHandler
from .util import abort_with_message


def get_client(endpoint_url: Optional[str] = None):
    """Return an S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        config=boto3.session.Config(
            s3={"addressing_style": "path"}, signature_version="s3v4"
        ),
    )


def get_object_name(checksum: str, prefix: Optional[str] = None):
    """Get the object name."""
    if prefix:
        return f"{prefix.rstrip('/')}/{checksum}"
    return checksum


class ObjectStorageFileHandler(FileHandler):
    """Handler for files on object storage (e.g. S3)."""

    URL_LIFETIME = 3600

    def __init__(
        self,
        handle,
        bucket_name: str,
        db_handle: DbReadBase,
        prefix: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        """Initialize self given a handle and media base directory."""
        super().__init__(handle, db_handle=db_handle)
        self.client = get_client(endpoint_url)
        self.bucket_name = bucket_name
        self.object_name = get_object_name(checksum=self.checksum, prefix=prefix)

    def _get_presigned_url(
        self, expires_in: float, download: bool = False, filename: str = ""
    ):
        """Get a presigned URL to a file object."""
        params = {
            "Bucket": self.bucket_name,
            "Key": self.object_name,
            "ResponseContentType": self.mime,
        }
        if download:
            params["ResponseContentDisposition"] = f"attachment; filename={filename}"
        try:
            response = self.client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in,
            )
        except ClientError as err:
            current_app.logger.error(err)
            return None
        return response

    def _download_fileobj(self) -> BinaryIO:
        """Download a binary file object."""
        try:
            response = self.client.get_object(
                Bucket=self.bucket_name, Key=self.object_name
            )
            return response["Body"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                abort_with_message(404, "Media file not found")
            else:
                abort_with_message(
                    500, f"Error retrieving media file: {exc.response['Error']['Code']}"
                )
            raise  # will never trigger - just to make mypy happy

    def get_file_object(self) -> BinaryIO:
        """Return a binary file object."""
        return self._download_fileobj()

    def file_exists(self) -> bool:
        """Check if the file exists."""
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=self.object_name)
            return True
        except ClientError:
            return False

    def get_file_size(self) -> int:
        """Return the file size in bytes."""
        try:
            response = self.client.head_object(
                Bucket=self.bucket_name, Key=self.object_name
            )
        except ClientError as exc:
            raise FileNotFoundError from exc
        file_size = response["ContentLength"]
        return file_size

    def send_file(
        self, etag: Optional[str] = None, download: bool = False, filename: str = ""
    ):
        """Send media file to client."""
        url = self._get_presigned_url(
            expires_in=self.URL_LIFETIME, download=download, filename=filename
        )
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
    prefix: Optional[str] = None,
    endpoint_url: Optional[str] = None,
) -> None:
    """Upload a file from a stream, returning the file path."""
    if not mime:
        raise ValueError("Missing MIME type")
    client = get_client(endpoint_url)
    object_name = get_object_name(checksum=checksum, prefix=prefix)
    client.upload_fileobj(
        stream, bucket_name, object_name, ExtraArgs={"ContentType": mime}
    )


def get_object_keys_size(
    bucket_name: str,
    prefix: Optional[str] = None,
    endpoint_url: Optional[str] = None,
) -> Dict[str, int]:
    """Return a dictionary with key and size of all objects in a bucket.

    Fetches 1000 objects at a time.
    """
    client = get_client(endpoint_url)
    keys = {}
    paginator = client.get_paginator("list_objects_v2")
    if prefix:
        response_iterator = paginator.paginate(Bucket=bucket_name, Prefix=f"{prefix}/")
    else:
        response_iterator = paginator.paginate(Bucket=bucket_name)
    for response in response_iterator:
        if "Contents" in response:
            contents = response["Contents"]
            keys.update(
                {
                    obj["Key"]: obj["Size"]
                    for obj in contents
                    if not prefix or obj["Key"].startswith(f"{prefix}/")
                }
            )
    return keys
